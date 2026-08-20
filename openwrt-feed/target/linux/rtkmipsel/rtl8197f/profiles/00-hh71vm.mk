#

#





#
# This is free software, licensed under the GNU General Public License v2.
#



# /proc/rtl865x/port_status.





define Profile/hh71vm
  NAME:=Alcatel LINKHUB HH71VM
  PRIORITY:=1
  PACKAGES:=swconfig kmod-rtl8192cd
endef

define Profile/hh71vm/Description
	Alcatel LINKHUB HH71VM (RTL8197FS + RTL8812FE), Realtek side
endef

$(eval $(call Profile,hh71vm))
