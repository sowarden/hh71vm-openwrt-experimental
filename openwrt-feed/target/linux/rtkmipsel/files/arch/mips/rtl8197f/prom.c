





















#include <linux/version.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/string.h>

#include <asm/bootinfo.h>
#include <asm/addrspace.h>

#include "bspcpu.h"
#include "bspchip.h"





unsigned int bsp_uart0_rbr = BSP_UART0_RBR_8197F;
unsigned int bsp_uart0_thr = BSP_UART0_THR_8197F;
EXPORT_SYMBOL(bsp_uart0_rbr);
EXPORT_SYMBOL(bsp_uart0_thr);

extern char arcs_cmdline[];

#ifdef CONFIG_EARLY_PRINTK
static int promcons_output __initdata = 0;











void __init unregister_prom_console(void)
{
	if (promcons_output)
		promcons_output = 0;
}

void __init disable_early_printk(void)
    __attribute__ ((alias("unregister_prom_console")));

void prom_putchar(char c)
{
	unsigned int busy_cnt = 0;

	do
	{
		/* Prevent Hanging */
		if (busy_cnt++ >= 30000)
		{
			/* Reset Tx FIFO */
			REG8(BSP_UART0_FCR) = BSP_TXRST | BSP_CHAR_TRIGGER_14;
			return;
		}
	} while ((REG8(BSP_UART0_LSR) & BSP_LSR_THRE) == BSP_TxCHAR_AVAIL);

	/* Send Character */
	REG8(BSP_UART0_THR) = c;
	return;
}

static int bsp_serial_init(void)
{
	if (IS_8197F_VG()) {
		bsp_uart0_rbr = BSP_UART0_RBR_8197F_VG;
		bsp_uart0_thr = BSP_UART0_THR_8197F_VG;
	}

	REG32(BSP_UART0_IER) = 0;

	REG32(BSP_UART0_LCR) = BSP_LCR_DLAB;
	REG32(BSP_UART0_DLL) = BSP_UART0_BAUD_DIVISOR & 0x00ff;
	REG32(BSP_UART0_DLM) = (BSP_UART0_BAUD_DIVISOR & 0xff00) >> 8;
	REG32(BSP_UART0_LCR) = BSP_CHAR_LEN_8;
	return 0;
}
#else
static int bsp_serial_init(void)
{
	return 0;
}
#endif

const char *get_system_type(void)
{
	return "RTL8197F";
}

void __init prom_free_prom_memory(void)
{
}






static __init void prom_init_cmdline(int argc, char **argv)
{
	int i;

	if (argc > 0 && argv) {
		for (i = 0; i < argc; i++) {
			if (!argv[i])
				continue;
			strlcat(arcs_cmdline, " ", sizeof(arcs_cmdline));
			strlcat(arcs_cmdline, argv[i], sizeof(arcs_cmdline));
		}
	} else {
		strcpy(arcs_cmdline, "console=ttyS0,38400");
	}
}


static __init u_long prom_detect_memsize(void)
{
	switch (REG32(BSP_BOND_OPTION) & 0x0F) {
	case 0x06:
	case 0x0C:
		return 32 << 20;
	case 0x04:
	case 0x0A:
		return 64 << 20;
	case 0x05:
	case 0x0B:
		return 128 << 20;
	default:
		return REG32(0xB8000F00) << 20;
	}
}

/* Do basic initialization */
void __init prom_init(void)
{
	u_long mem_size;

	bsp_serial_init();
	prom_init_cmdline(fw_arg0, (char **)fw_arg1);

	mem_size = prom_detect_memsize();
	add_memory_region(0, mem_size, BOOT_MEM_RAM);

#ifndef CONFIG_RTL_819X_SWCORE
	



#define SYS_CLK_MAG		(0xB8000000 + 0x0010)
#define CM_ACTIVE_SWCORE	(1 << 11)
#define EPHY_CONTROL		(0xB8000000 + 0x01E0)
#define EN_ROUTER_MODE		(1 << 12)
	REG32(SYS_CLK_MAG) &= ~CM_ACTIVE_SWCORE;
	REG32(EPHY_CONTROL) &= ~EN_ROUTER_MODE;
#endif
}
