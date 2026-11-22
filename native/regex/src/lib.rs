// SPDX-License-Identifier: MIT OR Apache-2.0
//! C ABI of the Loxia regex engine (ADR-0131).
//!
//! Two modes: `LINEAR` (the `regex` crate, linear time, the default) and `FULL`
//! (`fancy-regex`, backtracking with a step limit, for backreferences and
//! lookaround). Every `extern "C"` entry point is wrapped in `catch_unwind`,
//! and the panic hook is silenced at init so a Rust panic never reaches stderr
//! (stderr is an I1 channel; ADR-0131 §2).
//!
//! Offsets that cross the ABI are code points, like Loxia strings (ADR-0035).

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::{Mutex, Once, OnceLock};

use fancy_regex::RegexBuilder as FullBuilder;
use regex::RegexBuilder as LinearBuilder;

pub const ABI_VERSION: u32 = 2;

pub const MODE_LINEAR: u32 = 0;
pub const MODE_FULL: u32 = 1;

pub const FLAG_CASELESS: u32 = 1;
pub const FLAG_MULTILINE: u32 = 2;
pub const FLAG_DOTALL: u32 = 4;
pub const FLAG_EXTENDED: u32 = 8;

pub const OK: i32 = 0;
pub const NO_MATCH: i32 = -100;
pub const ERR_PANIC: i32 = -1;
pub const ERR_ARGS: i32 = -2;
pub const ERR_MODE: i32 = -3;
pub const ERR_LIMIT: i32 = -4;
pub const ERR_HANDLE: i32 = -5;
pub const ERR_UTF8: i32 = -6;
pub const ERR_HANDLES: i32 = -7;
pub const ERR_CAPACITY: i32 = -8;
pub const ERR_TOO_BIG: i32 = -9;
pub const ERR_COMPILE: i32 = -10;

/// Upper bound on live compiled patterns; keeps the table bounded and the
/// failure deterministic.
const MAX_HANDLES: usize = 4096;
/// Backtracking steps allowed in `FULL` mode, fixed for determinism.
const BACKTRACK_LIMIT: usize = 1_000_000;
/// Compiled-program memory cap for `LINEAR` mode.
const SIZE_LIMIT: usize = 10 * 1024 * 1024;

enum Engine {
    Linear(regex::Regex),
    Full(fancy_regex::Regex),
}

struct Slots {
    engines: Vec<Option<Engine>>,
    free: Vec<usize>,
}

static SLOTS: OnceLock<Mutex<Slots>> = OnceLock::new();

fn slots() -> &'static Mutex<Slots> {
    SLOTS.get_or_init(|| {
        Mutex::new(Slots {
            engines: Vec::new(),
            free: Vec::new(),
        })
    })
}

/// Installs a silent panic hook once. Without it, `catch_unwind` still lets the
/// default hook print `thread ... panicked` on stderr.
fn init() {
    static HOOK: Once = Once::new();
    HOOK.call_once(|| {
        std::panic::set_hook(Box::new(|_| {}));
    });
}

/// Why a pattern failed to build: the stable ABI code plus the byte offset of a
/// syntax error (`-1` when the failure is not a syntax error or is unknown).
#[derive(Debug)]
struct BuildFailure {
    code: i32,
    offset: i64,
}

impl BuildFailure {
    fn new(code: i32) -> BuildFailure {
        BuildFailure { code, offset: -1 }
    }
}

fn build(
    pattern: &str,
    flags: u32,
    mode: u32,
    backtrack_limit: usize,
) -> Result<Engine, BuildFailure> {
    match mode {
        MODE_LINEAR => {
            let mut builder = LinearBuilder::new(pattern);
            builder.size_limit(SIZE_LIMIT);
            if flags & FLAG_CASELESS != 0 {
                builder.case_insensitive(true);
            }
            if flags & FLAG_MULTILINE != 0 {
                builder.multi_line(true);
            }
            if flags & FLAG_DOTALL != 0 {
                builder.dot_matches_new_line(true);
            }
            if flags & FLAG_EXTENDED != 0 {
                builder.ignore_whitespace(true);
            }
            match builder.build() {
                Ok(regex) => Ok(Engine::Linear(regex)),
                Err(regex::Error::CompiledTooBig(_)) => Err(BuildFailure::new(ERR_TOO_BIG)),
                Err(regex::Error::Syntax(_)) => Err(BuildFailure {
                    code: ERR_COMPILE,
                    offset: linear_offset(pattern, flags),
                }),
                Err(_) => Err(BuildFailure::new(ERR_COMPILE)),
            }
        }
        MODE_FULL => {
            let mut builder = FullBuilder::new(pattern);
            builder.backtrack_limit(backtrack_limit);
            if flags & FLAG_CASELESS != 0 {
                builder.case_insensitive(true);
            }
            if flags & FLAG_MULTILINE != 0 {
                builder.multi_line(true);
            }
            if flags & FLAG_DOTALL != 0 {
                builder.dot_matches_new_line(true);
            }
            if flags & FLAG_EXTENDED != 0 {
                builder.ignore_whitespace(true);
            }
            match builder.build() {
                Ok(regex) => Ok(Engine::Full(regex)),
                Err(error) => Err(full_failure(pattern, flags, &error)),
            }
        }
        _ => Err(BuildFailure::new(ERR_MODE)),
    }
}

/// Byte offset of the first syntax error according to `regex-syntax` (the parser
/// behind the linear engine); `-1` when the pattern parses.
fn linear_offset(pattern: &str, flags: u32) -> i64 {
    let mut builder = regex_syntax::ParserBuilder::new();
    builder.ignore_whitespace(flags & FLAG_EXTENDED != 0);
    match builder.build().parse(pattern) {
        Ok(_) => -1,
        Err(error) => syntax_error_offset(&error),
    }
}

fn syntax_error_offset(error: &regex_syntax::Error) -> i64 {
    match error {
        regex_syntax::Error::Parse(inner) => inner.span().start.offset as i64,
        regex_syntax::Error::Translate(inner) => inner.span().start.offset as i64,
        _ => -1,
    }
}

/// Maps a `FULL` build error to the ABI code and offset. When both parsers
/// reject the pattern, the linear span is the canonical offset: `fancy-regex`
/// points at the end of an unclosed group while `regex-syntax` points at the
/// opening delimiter, and I1 requires the same answer in both modes.
fn full_failure(pattern: &str, flags: u32, error: &fancy_regex::Error) -> BuildFailure {
    match error {
        fancy_regex::Error::ParseError(position, _) => {
            let linear = linear_offset(pattern, flags);
            BuildFailure {
                code: ERR_COMPILE,
                offset: if linear >= 0 {
                    linear
                } else {
                    *position as i64
                },
            }
        }
        fancy_regex::Error::CompileError(inner) => {
            if let fancy_regex::CompileError::InnerError(build) = inner.as_ref() {
                if let Some(syntax) = build.syntax_error() {
                    return BuildFailure {
                        code: ERR_COMPILE,
                        offset: syntax_error_offset(syntax),
                    };
                }
                if build.size_limit().is_some() {
                    return BuildFailure::new(ERR_TOO_BIG);
                }
            }
            if matches!(
                inner.as_ref(),
                fancy_regex::CompileError::PatternTooComplex
                    | fancy_regex::CompileError::DfaBuildError(..)
            ) {
                return BuildFailure::new(ERR_TOO_BIG);
            }
            BuildFailure::new(ERR_COMPILE)
        }
        _ => BuildFailure::new(ERR_COMPILE),
    }
}

/// Converts a code-point offset to a UTF-8 byte offset. `None` when the offset
/// is past the end of the string.
fn byte_index(text: &str, code_points: usize) -> Option<usize> {
    let mut chars = text.char_indices();
    for _ in 0..code_points {
        chars.next()?;
    }
    Some(chars.next().map(|(byte, _)| byte).unwrap_or(text.len()))
}

fn code_point(text: &str, byte: usize) -> i64 {
    text[..byte].chars().count() as i64
}

fn write_spans<F>(
    text: &str,
    groups: usize,
    group: F,
    out: *mut i64,
    capacity: usize,
) -> i32
where
    F: Fn(usize) -> Option<(usize, usize)>,
{
    if groups * 2 > capacity {
        return ERR_CAPACITY;
    }
    let mut written = 0usize;
    for index in 0..groups {
        if written + 2 > capacity {
            break;
        }
        let (start, end) = match group(index) {
            Some((start, end)) => (code_point(text, start), code_point(text, end)),
            None => (-1, -1),
        };
        unsafe {
            *out.add(written) = start;
            *out.add(written + 1) = end;
        }
        written += 2;
    }
    written as i32
}

#[no_mangle]
pub extern "C" fn loxr_abi_version() -> u32 {
    init();
    ABI_VERSION
}

#[no_mangle]
pub extern "C" fn loxr_compile(
    pattern: *const u8,
    len: usize,
    flags: u32,
    mode: u32,
    out_handle: *mut i64,
    out_offset: *mut i64,
) -> i32 {
    init();
    catch_unwind(AssertUnwindSafe(|| {
        if !out_offset.is_null() {
            unsafe { *out_offset = -1 };
        }
        if pattern.is_null() || out_handle.is_null() {
            return ERR_ARGS;
        }
        let bytes = unsafe { std::slice::from_raw_parts(pattern, len) };
        let Ok(text) = std::str::from_utf8(bytes) else {
            return ERR_UTF8;
        };
        #[cfg(test)]
        if text == "__LOX_TEST_PANIC__" {
            panic!("boom");
        }
        let engine = match build(text, flags, mode, BACKTRACK_LIMIT) {
            Ok(engine) => engine,
            Err(failure) => {
                if !out_offset.is_null() {
                    unsafe { *out_offset = failure.offset };
                }
                return failure.code;
            }
        };
        let mut state = slots().lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let index = match state.free.pop() {
            Some(index) => {
                state.engines[index] = Some(engine);
                index
            }
            None => {
                if state.engines.len() >= MAX_HANDLES {
                    return ERR_HANDLES;
                }
                state.engines.push(Some(engine));
                state.engines.len() - 1
            }
        };
        unsafe {
            *out_handle = index as i64 + 1;
            if !out_offset.is_null() {
                *out_offset = -1;
            }
        }
        OK
    }))
    .unwrap_or(ERR_PANIC)
}

#[no_mangle]
pub extern "C" fn loxr_match(
    handle: i64,
    subject: *const u8,
    len: usize,
    start: usize,
    out: *mut i64,
    capacity: usize,
) -> i32 {
    init();
    catch_unwind(AssertUnwindSafe(|| {
        if subject.is_null() || out.is_null() || handle < 1 {
            return ERR_ARGS;
        }
        let bytes = unsafe { std::slice::from_raw_parts(subject, len) };
        let Ok(text) = std::str::from_utf8(bytes) else {
            return ERR_UTF8;
        };
        #[cfg(test)]
        if text == "__LOX_TEST_PANIC__" {
            panic!("boom");
        }
        let state = slots().lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(Some(engine)) = state.engines.get((handle - 1) as usize) else {
            return ERR_HANDLE;
        };
        let Some(byte_start) = byte_index(text, start) else {
            return NO_MATCH;
        };
        match engine {
            Engine::Linear(re) => match re.captures_at(text, byte_start) {
                Some(caps) => write_spans(
                    text,
                    caps.len(),
                    |index| caps.get(index).map(|m| (m.start(), m.end())),
                    out,
                    capacity,
                ),
                None => NO_MATCH,
            },
            Engine::Full(re) => match re.captures_from_pos(text, byte_start) {
                Ok(Some(caps)) => write_spans(
                    text,
                    caps.len(),
                    |index| caps.get(index).map(|m| (m.start(), m.end())),
                    out,
                    capacity,
                ),
                Ok(None) => NO_MATCH,
                Err(_) => ERR_LIMIT,
            },
        }
    }))
    .unwrap_or(ERR_PANIC)
}

/// Writes the capture-group names of `handle`, each followed by a NUL byte: group
/// 0 is always empty, an unnamed group is empty. With `out == NULL` returns the
/// needed byte count (so the caller can size the buffer); with a smaller
/// `capacity` returns `ERR_CAPACITY`.
#[no_mangle]
pub extern "C" fn loxr_group_names(handle: i64, out: *mut u8, capacity: usize) -> i32 {
    init();
    catch_unwind(AssertUnwindSafe(|| {
        #[cfg(test)]
        if handle == i64::MIN {
            panic!("boom");
        }
        if handle < 1 {
            return ERR_ARGS;
        }
        let state = slots().lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(Some(engine)) = state.engines.get((handle - 1) as usize) else {
            return ERR_HANDLE;
        };
        let names: Vec<Option<&str>> = match engine {
            Engine::Linear(re) => re.capture_names().collect(),
            Engine::Full(re) => re.capture_names().collect(),
        };
        let mut buffer = Vec::with_capacity(names.len());
        for name in &names {
            if let Some(name) = name {
                buffer.extend_from_slice(name.as_bytes());
            }
            buffer.push(0);
        }
        if out.is_null() {
            return buffer.len() as i32;
        }
        if buffer.len() > capacity {
            return ERR_CAPACITY;
        }
        if !buffer.is_empty() {
            unsafe { std::ptr::copy_nonoverlapping(buffer.as_ptr(), out, buffer.len()) };
        }
        buffer.len() as i32
    }))
    .unwrap_or(ERR_PANIC)
}

#[no_mangle]
pub extern "C" fn loxr_free(handle: i64) {
    init();
    let _ = catch_unwind(AssertUnwindSafe(|| {
        #[cfg(test)]
        if handle == i64::MIN {
            panic!("boom");
        }
        if handle < 1 {
            return;
        }
        let index = (handle - 1) as usize;
        let mut state = slots().lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(slot) = state.engines.get_mut(index) {
            if slot.take().is_some() {
                state.free.push(index);
            }
        }
    }));
}

#[cfg(test)]
mod tests {
    use super::*;

    fn compile(pattern: &str, flags: u32, mode: u32) -> i64 {
        let bytes = pattern.as_bytes();
        let mut handle = 0i64;
        let mut offset = 0i64;
        let code = loxr_compile(
            bytes.as_ptr(),
            bytes.len(),
            flags,
            mode,
            &mut handle,
            &mut offset,
        );
        assert_eq!(code, OK, "compile failed for {pattern:?}");
        handle
    }

    fn try_match(handle: i64, subject: &str, start: usize) -> (i32, Vec<i64>) {
        let bytes = subject.as_bytes();
        let mut spans = vec![0i64; 32];
        let code = loxr_match(
            handle,
            bytes.as_ptr(),
            bytes.len(),
            start,
            spans.as_mut_ptr(),
            spans.len(),
        );
        if code < 0 {
            return (code, Vec::new());
        }
        spans.truncate(code as usize);
        (code, spans)
    }

    fn compile_with_limit(pattern: &str, mode: u32, limit: usize) -> i64 {
        let engine = build(pattern, 0, mode, limit).expect("pattern must compile");
        let mut state = slots().lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        state.engines.push(Some(engine));
        state.engines.len() as i64
    }

    fn compile_error(pattern: &str, flags: u32, mode: u32) -> (i32, i64) {
        let bytes = pattern.as_bytes();
        let mut handle = 0i64;
        let mut offset = 0i64;
        let code = loxr_compile(
            bytes.as_ptr(),
            bytes.len(),
            flags,
            mode,
            &mut handle,
            &mut offset,
        );
        (code, offset)
    }

    #[test]
    fn linear_reports_code_point_offsets() {
        let handle = compile(r"\p{L}+", 0, MODE_LINEAR);
        let (code, spans) = try_match(handle, "café ☕ 123", 0);
        assert_eq!(code, 2);
        assert_eq!(spans, vec![0, 4]);
        loxr_free(handle);
    }

    #[test]
    fn full_supports_backreferences() {
        let handle = compile(r"(\w+)\s+\1", 0, MODE_FULL);
        let (code, spans) = try_match(handle, "hello hello world", 0);
        assert_eq!(code, 4);
        assert_eq!(spans[0..2], [0, 11]);
        assert_eq!(spans[2..4], [0, 5]);
        loxr_free(handle);
    }

    #[test]
    fn no_match_is_distinct_from_errors() {
        let handle = compile("z+", 0, MODE_LINEAR);
        let (code, _) = try_match(handle, "abc", 0);
        assert_eq!(code, NO_MATCH);
        loxr_free(handle);
    }

    #[test]
    fn syntax_error_reports_the_byte_offset_in_both_modes() {
        for mode in [MODE_LINEAR, MODE_FULL] {
            assert_eq!(compile_error("(", 0, mode), (ERR_COMPILE, 0));
            assert_eq!(compile_error("a(b", 0, mode), (ERR_COMPILE, 1));
            assert_eq!(compile_error("é(", 0, mode), (ERR_COMPILE, 2));
            assert_eq!(compile_error(r"\p{Foo}", 0, mode), (ERR_COMPILE, 0));
        }
    }

    #[test]
    fn full_only_syntax_error_uses_the_engine_offset() {
        // The linear parser accepts `a**`, so the fancy position (2) is the only
        // available offset.
        assert_eq!(compile_error("a**", 0, MODE_FULL), (ERR_COMPILE, 2));
    }

    #[test]
    fn too_big_pattern_is_a_stable_error_without_offset() {
        for mode in [MODE_LINEAR, MODE_FULL] {
            assert_eq!(compile_error("a{1000000}", 0, mode), (ERR_TOO_BIG, -1));
        }
    }


    #[test]
    fn invalid_mode_is_rejected() {
        let bytes = b"a";
        let mut handle = 0i64;
        let mut offset = 0i64;
        let code = loxr_compile(
            bytes.as_ptr(),
            bytes.len(),
            0,
            9,
            &mut handle,
            &mut offset,
        );
        assert_eq!(code, ERR_MODE);
    }

    #[test]
    fn unknown_handle_is_an_error() {
        let (code, _) = try_match(999_999, "abc", 0);
        assert_eq!(code, ERR_HANDLE);
        loxr_free(999_999);
    }

    #[test]
    fn group_names_are_reported() {
        let names = |pattern: &str, mode: u32| {
            let handle = compile(pattern, 0, mode);
            let needed = loxr_group_names(handle, std::ptr::null_mut(), 0);
            assert!(needed > 0, "pattern {pattern} has at least group 0");
            let mut buffer = vec![0u8; needed as usize];
            assert_eq!(loxr_group_names(handle, buffer.as_mut_ptr(), buffer.len()), needed);
            loxr_free(handle);
            buffer[..buffer.len() - 1]
                .split(|byte| *byte == 0)
                .map(|part| String::from_utf8(part.to_vec()).unwrap())
                .collect::<Vec<_>>()
        };
        assert_eq!(names("([a-z]+) +([0-9]+)", MODE_LINEAR), vec!["", "", ""]);
        assert_eq!(
            names("(?P<word>[a-z]+)(?P<num>[0-9]+)", MODE_LINEAR),
            vec!["", "word", "num"]
        );
        assert_eq!(
            names("(?P<a>a)(?P<b>b)", MODE_FULL),
            vec!["", "a", "b"]
        );
    }

    #[test]
    fn free_is_idempotent() {
        let handle = compile("a", 0, MODE_LINEAR);
        loxr_free(handle);
        loxr_free(handle);
    }

    #[test]
    fn insufficient_capacity_is_reported() {
        let handle = compile(r"(a)(b)", 0, MODE_LINEAR);
        let subject = "ab";
        let bytes = subject.as_bytes();
        let mut spans = vec![0i64; 2];
        let code = loxr_match(
            handle,
            bytes.as_ptr(),
            bytes.len(),
            0,
            spans.as_mut_ptr(),
            spans.len(),
        );
        assert_eq!(code, ERR_CAPACITY);
        loxr_free(handle);
    }

    #[test]
    fn backtrack_limit_is_reported() {
        let handle = compile_with_limit(r"(a+)\1$", MODE_FULL, 10);
        let subject = "a".repeat(200);
        let (code, _) = try_match(handle, &subject, 0);
        assert_eq!(code, ERR_LIMIT);
        loxr_free(handle);
    }

    #[test]
    fn start_offset_is_in_code_points() {
        let handle = compile(r"\w+", 0, MODE_LINEAR);
        let (code, spans) = try_match(handle, "ab cd", 3);
        assert_eq!(code, 2);
        assert_eq!(spans, vec![3, 5]);
        loxr_free(handle);
    }

    #[test]
    fn caseless_flag_applies() {
        let handle = compile("abc", FLAG_CASELESS, MODE_LINEAR);
        let (code, _) = try_match(handle, "ABC", 0);
        assert_eq!(code, 2);
        loxr_free(handle);
    }

    #[test]
    fn panic_does_not_escape_any_entry_point() {
        let pattern = b"__LOX_TEST_PANIC__";
        let mut handle = 0i64;
        let mut offset = -1i64;
        let code = loxr_compile(
            pattern.as_ptr(),
            pattern.len(),
            0,
            MODE_LINEAR,
            &mut handle,
            &mut offset,
        );
        assert_eq!(code, ERR_PANIC);

        let handle = compile("a", 0, MODE_LINEAR);
        let subject = "__LOX_TEST_PANIC__";
        let mut spans = [0i64; 2];
        let code = loxr_match(
            handle,
            subject.as_ptr(),
            subject.len(),
            0,
            spans.as_mut_ptr(),
            spans.len(),
        );
        assert_eq!(code, ERR_PANIC);

        assert_eq!(loxr_group_names(i64::MIN, std::ptr::null_mut(), 0), ERR_PANIC);
        loxr_free(i64::MIN);
        loxr_free(handle);
    }
}
