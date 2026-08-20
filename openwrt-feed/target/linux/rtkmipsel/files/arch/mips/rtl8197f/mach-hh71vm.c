







#include <linux/init.h>
#include <linux/gpio.h>
#include <linux/leds.h>

#include "machtypes.h"
#include "dev_leds_gpio.h"
#include "dev-gpio-buttons.h"




















static void __init hh71vm_setup(void)
{
}

MIPS_MACHINE(RTL8197_MACH_HH71VM, "HH71VM", "Alcatel LINKHUB HH71 series",
	     hh71vm_setup);
