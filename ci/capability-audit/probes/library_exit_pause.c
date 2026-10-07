/* Diagnostic only: inspect the loaded DSOs before the empty-main exit case. */
#include <signal.h>

int main(void)
{
    raise(SIGSTOP);
    return 0;
}
