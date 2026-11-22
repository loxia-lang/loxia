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

pub const ABI_VERSION: u32 = 1;

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

fn build(
    pattern: &str,
    flags: u32,
    mode: u32,
    backtrack_limit: usize,
) -> Result<Engine, i32> {
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
            builder.build().map(Engine::Linear).map_err(|_| ERR_COMPILE)
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
            builder.build().map(Engine::Full).map_err(|_| ERR_COMPILE)
        }
        _ => Err(ERR_MODE),
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
        if pattern.is_null() || out_handle.is_null() {
            return ERR_ARGS;
        }
        let bytes = unsafe { std::slice::from_raw_parts(pattern, len) };
        let Ok(text) = std::str::from_utf8(bytes) else {
            return ERR_UTF8;
        };
        let engine = match build(text, flags, mode, BACKTRACK_LIMIT) {
            Ok(engine) => engine,
            Err(code) => return code,
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

#[no_mangle]
pub extern "C" fn loxr_free(handle: i64) {
    init();
    let _ = catch_unwind(AssertUnwindSafe(|| {
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
    fn syntax_error_returns_compile_code() {
        let bytes = b"(";
        let mut handle = 0i64;
        let mut offset = 0i64;
        let code = loxr_compile(
            bytes.as_ptr(),
            bytes.len(),
            0,
            MODE_LINEAR,
            &mut handle,
            &mut offset,
        );
        assert_eq!(code, ERR_COMPILE);
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
    fn panic_does_not_escape() {
        let code = catch_unwind(|| panic!("boom")).unwrap_or(ERR_PANIC);
        assert_eq!(code, ERR_PANIC);
    }
}
