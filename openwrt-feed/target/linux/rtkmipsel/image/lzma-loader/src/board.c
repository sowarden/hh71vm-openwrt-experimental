

























#include <stddef.h>

#define BSP_ECO_SN          0xB8000000

#define BSP_UART0_BASE      0xB8147000
#define UART_THR_8197F      (BSP_UART0_BASE + 0x024)
#define UART_THR_8197F_VG   (BSP_UART0_BASE + 0x000)
#define UART_LSR            (BSP_UART0_BASE + 0x014)

#define REG8(reg)   (*(volatile unsigned char   *)((unsigned int)reg))
#define REG32(reg)  (*(volatile unsigned int    *)((unsigned int)reg))

static unsigned int uart_thr(void)
{
	if ((REG32(BSP_ECO_SN) & 0xFFFFF000) == 0x81970000)
		return UART_THR_8197F_VG;

	return UART_THR_8197F;
}

void serial_outc(char c)
{
        int i=0;

        while (1)
        {
                i++;
                if (i >=0x6000)
                        break;
                if (REG8(UART_LSR) & 0x20)
                        break;
        }
        REG8(uart_thr()) = (c);
}


void board_putc(int ch)
{
	serial_outc(ch);
}

void board_init(void)
{
}
