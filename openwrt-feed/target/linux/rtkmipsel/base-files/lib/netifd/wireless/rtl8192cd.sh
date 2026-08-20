#!/bin/sh
# netifd driver for vendor rtl8192cd: RTL8197F 2.4 GHz and RTL8812FE 5 GHz.
#
# rtl8192cd is not a cfg80211 driver in this build. It is configured through private
# Wireless Extensions ioctls (`iwpriv <if> set_mib field=value`), so the standard
# mac80211 handler cannot manage it. This file implements netifd's supported wireless
# driver extension point and provides UCI, LuCI, wifi up/down/reload, and bridge setup.
#
# Hardware-verified details:
#
# 1. wpa2_cipher/wpa_cipher are bit masks based on the RSN suite number. CCMP is
#    BIT(3)=8 and TKIP is BIT(1)=2. encmode is a separate enumeration where TKIP=2
#    and CCMP=4.
# 2. Derive 11n/11ac from htmode, not enable_ht. Modern `hwmode 11g` plus `htmode
#    HT20` otherwise incorrectly starts as pure b/g.
# 3. netifd scans /lib/netifd/wireless only once at startup. This handler must exist
#    before netifd starts.
#
# hostapd is not used; the vendor driver contains its own PSK implementation.

. /lib/netifd/netifd-wireless.sh
. /lib/functions.sh

init_wireless_driver "$@"

drv_rtl8192cd_init_device_config() {
	# A radio is bound to its fixed driver netdev (wlan0/wlan1). Without ifname,
	# derive it from the UCI section name: radio0 -> wlan0.
	config_add_string ifname
}

drv_rtl8192cd_init_iface_config() {
	config_add_boolean hidden
}

# Convert htmode into 11n/11ac band bits, channel width, and secondary-channel
# offset. use40M: 0=20 MHz, 1=40 MHz, 2=80 MHz, 3=160 MHz.
# 2ndchoffset: 0=irrelevant, 1=below primary, 2=above primary. At VHT80 the
# driver calculates the offset itself.
rtl_parse_htmode() {
	local ht="$1"

	ht_bit=0
	vht_bit=0
	use40m=0
	choffset=0

	case "$ht" in
		VHT*) ht_bit=8; vht_bit=64 ;;
		HT*)  ht_bit=8 ;;
	esac
	case "$ht" in
		HT40+|VHT40+) use40m=1; choffset=2 ;;
		HT40-|VHT40-) use40m=1; choffset=1 ;;
		HT40|VHT40)   use40m=1 ;;
		VHT80)        use40m=2 ;;
		VHT160)       use40m=3 ;;
	esac
}

# `band` is the vendor NETWORK_TYPE bit mask:
# 1|2|8 = 11b|11g|11n; 4|8|64 = 11a|11n|11ac.
rtl_band_mask() {
	case "$1" in
		a) echo $((4 + ht_bit + vht_bit)) ;;
		b) echo 1 ;;
		*) echo $((3 + ht_bit)) ;;
	esac
}

# The first wifi-iface uses the radio netdev. Additional interfaces use the
# pre-created vendor VAP names wlanX-va0 through wlanX-va3.
rtl_vif_ifname() {
	local base="$1" idx="$2"

	if [ "$idx" = 0 ]; then
		echo "$base"
	else
		echo "$base-va$((idx - 1))"
	fi
}

rtl_setup_vif() {
	local name="$1"
	local ifname
	local ssid key encryption hidden
	local wpa auth_type wpa_cipher
	local psk_enable=0 encmode=0 cipher_mask=0

	ifname="$(rtl_vif_ifname "$dev_ifname" "$vif_idx")"
	vif_idx=$((vif_idx + 1))

	json_select config
	json_get_vars ssid key hidden
	wireless_vif_parse_encryption
	json_select ..

	[ -d "/proc/$ifname" ] || {
		wireless_setup_vif_failed NO_SUCH_INTERFACE
		return 1
	}

	case "$wpa_cipher" in
		*CCMP*TKIP*|*TKIP*CCMP*) cipher_mask=10; encmode=4 ;;
		*CCMP*)                  cipher_mask=8;  encmode=4 ;;
		*TKIP*)                  cipher_mask=2;  encmode=2 ;;
	esac
	case "$auth_type" in
		psk)  psk_enable="$wpa" ;;   # 1=WPA, 2=WPA2, 3=mixed.
		none) psk_enable=0; encmode=0; cipher_mask=0 ;;
		*)
			# The built-in vendor PSK path does not support WEP, EAP, SAE/WPA3, or OWE.
			wireless_setup_vif_failed UNSUPPORTED_ENCRYPTION
			return 1
		;;
	esac

	ifconfig "$ifname" down

	iwpriv "$ifname" set_mib ssid="$ssid"
	iwpriv "$ifname" set_mib band="$band"
	iwpriv "$ifname" set_mib channel="$channel"
	iwpriv "$ifname" set_mib use40M="$use40m"
	iwpriv "$ifname" set_mib 2ndchoffset="$choffset"
	iwpriv "$ifname" set_mib opmode=16                  # 0x10 = AP
	iwpriv "$ifname" set_mib hiddenAP="${hidden:-0}"
	iwpriv "$ifname" set_mib authtype=0                 # Open authentication for WPA2.
	iwpriv "$ifname" set_mib psk_enable="$psk_enable"
	iwpriv "$ifname" set_mib encmode="$encmode"
	[ "$psk_enable" = 0 ] || {
		iwpriv "$ifname" set_mib wpa_cipher="$cipher_mask"
		iwpriv "$ifname" set_mib wpa2_cipher="$cipher_mask"
		iwpriv "$ifname" set_mib passphrase="$key"
	}

	ifconfig "$ifname" up

	wireless_add_vif "$name" "$ifname"
}

drv_rtl8192cd_setup() {
	local dev="$1"
	local dev_ifname raw_htmode band vif_idx=0
	local ht_bit vht_bit use40m choffset

	json_select config
	json_get_vars ifname
	json_get_var raw_htmode htmode
	json_select ..

	dev_ifname="${ifname:-wlan${dev#radio}}"

	[ -d "/proc/$dev_ifname" ] || {
		wireless_setup_failed NO_SUCH_INTERFACE
		return 1
	}

	rtl_parse_htmode "$raw_htmode"
	# netifd populates hwmode and channel before calling this handler.
	band="$(rtl_band_mask "$hwmode")"

	for_each_interface "ap" rtl_setup_vif

	wireless_set_up
}

drv_rtl8192cd_teardown() {
	local dev="$1"
	local dev_ifname vif

	json_select config
	json_get_vars ifname
	json_select ..

	dev_ifname="${ifname:-wlan${dev#radio}}"

	# Bring down the physical radio and every pre-created VAP. An extra down on an
	# unused interface is harmless, while active VAP membership is unavailable here.
	for vif in "$dev_ifname" "$dev_ifname"-va0 "$dev_ifname"-va1 "$dev_ifname"-va2 "$dev_ifname"-va3; do
		[ -d "/proc/$vif" ] && ifconfig "$vif" down 2>/dev/null
	done
}

drv_rtl8192cd_cleanup() {
	return 0
}

add_driver rtl8192cd
