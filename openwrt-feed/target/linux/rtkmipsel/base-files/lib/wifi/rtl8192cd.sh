# Radio detection for `wifi config`. This creates /etc/config/wireless when absent.
# Non-cfg80211 drivers use the standard /lib/wifi extension point. The companion
# net hotplug script triggers detection when wlan0 or wlan1 appears.
#
# Detection is idempotent: configured radios are skipped and numbering continues at
# the first unused radioN section.

append DRIVERS "rtl8192cd"

# Physical radios are fixed netdevs wlan0 and wlan1. VAP and WDS interfaces belong to
# their parent radio and are not enumerated here.
rtl8192cd_radios() {
	local dir
	for dir in /proc/wlan[0-9]; do
		[ -d "$dir" ] || continue
		echo "${dir##*/}"
	done
}

# The 5 GHz radio exposes 5 GHz calibration fields in mib_rf. The reference unit uses
# RTL8812FE and therefore defaults to VHT80. A different 5 GHz device would require an
# explicit capability check before this default could be considered portable.
rtl8192cd_is_5g() {
	grep -q 5GHT40 "/proc/$1/mib_rf" 2>/dev/null
}

detect_rtl8192cd() {
	local devidx=0
	local dev type known ifname channel hwmode htmode ssid

	config_load wireless

	while :; do
		config_get type "radio$devidx" type
		[ -n "$type" ] || break
		devidx=$((devidx + 1))
	done

	for dev in $(rtl8192cd_radios); do
		known=0
		config_foreach rtl8192cd_check_device wifi-device "$dev"
		[ "$known" -gt 0 ] && continue

		if rtl8192cd_is_5g "$dev"; then
			channel=36          # Lower UNII-1, outside DFS.
			hwmode=11a
			htmode=VHT80
			ssid=HH71VM-5G
		else
			channel=6
			hwmode=11g
			htmode=HT20
			ssid=HH71VM
		fi

		# The public default key is an acknowledged test-image compromise. It is safer
		# than an open AP on a router with mobile Internet, but must be replaced before
		# any non-isolated use. A future release should read a factory key safely.
		uci -q batch <<-EOF
			set wireless.radio${devidx}=wifi-device
			set wireless.radio${devidx}.type=rtl8192cd
			set wireless.radio${devidx}.ifname=${dev}
			set wireless.radio${devidx}.channel=${channel}
			set wireless.radio${devidx}.hwmode=${hwmode}
			set wireless.radio${devidx}.htmode=${htmode}
			set wireless.radio${devidx}.disabled=0

			set wireless.default_radio${devidx}=wifi-iface
			set wireless.default_radio${devidx}.device=radio${devidx}
			set wireless.default_radio${devidx}.network=lan
			set wireless.default_radio${devidx}.mode=ap
			set wireless.default_radio${devidx}.ssid=${ssid}
			set wireless.default_radio${devidx}.encryption=psk2+ccmp
			set wireless.default_radio${devidx}.key=hh71vm12345
		EOF
		uci -q commit wireless

		devidx=$((devidx + 1))
	done
}

rtl8192cd_check_device() {
	local cfg="$1" dev="$2"
	local cfgtype cfgif

	config_get cfgtype "$cfg" type
	[ "$cfgtype" = rtl8192cd ] || return 0

	config_get cfgif "$cfg" ifname
	# A section without ifname is bound by name: radio0 -> wlan0.
	[ -n "$cfgif" ] || cfgif="wlan${cfg#radio}"

	[ "$cfgif" = "$dev" ] && known=1
}
