#include <stdint.h>

uintptr_t __stack_chk_guard = 0x42b16f00a0c0d0e0ULL;

int __android_log_print(int priority, const char *tag, const char *format, ...) {
    (void)priority;
    (void)tag;
    (void)format;
    return 0;
}
