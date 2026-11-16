/*
 * Gerado por `runtime/gen_kernel.py` a partir de
 * `loxia_core/execution/primitives.py`. NÃO EDITE À MÃO.
 *
 * Cada declaração é a assinatura que o lowering usa; o `kernel.c` inclui este
 * header, então tabela e definição C não podem divergir sem quebrar o build
 * (ADR-0071, ADR-0094).
 */
#ifndef LOX_KERNEL_GEN_H
#define LOX_KERNEL_GEN_H

#include <stdint.h>

/* substr */
void * lox_substr(const void *, int64_t, int64_t);
/* join */
void * lox_join(const void *, const void *);
/* charCodeAt */
int64_t lox_char_code_at(const void *, int64_t);
/* fromCodePoint */
void * lox_from_code_point(int64_t);
/* args */
void * lox_args(void);
/* io.readFile */
void * lox_io_read_file(const void *);
/* io.readAll */
void * lox_io_read_all(void);
/* io.write */
void lox_io_write(const void *);
/* io.writeErr */
void lox_io_write_err(const void *);
/* io.writeFile */
int32_t lox_io_write_file(const void *, const void *);
/* io.readLine */
void * lox_io_read_line(void);
/* io.readUtf8 */
void * lox_io_read_utf8(int64_t, int32_t, int32_t);
/* io.flush */
void lox_io_flush(void);
/* fs.exists */
int32_t lox_fs_exists(const void *);
/* fs.listDir */
void * lox_fs_list_dir(const void *);
/* os.exit */
void lox_os_exit(int64_t);
/* os.getenv */
void * lox_os_getenv(const void *);
/* time.now */
int64_t lox_time_now(void);
/* time.sleep */
void lox_time_sleep(int64_t);

#endif /* LOX_KERNEL_GEN_H */
