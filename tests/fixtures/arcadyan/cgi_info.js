
var manufacturer='ARLT';
var isp='Orange';
var wan_mac_addr='60:8d:26:00:00:17';
var wan_mode='GPON';
var defroute_wan_ip="203.0.113.10";
var ipv6_info_buf="/";
var system={"cpuLoad":"12%", "total_mem":"400 MB", "free_mem":"150 MB", "total_flash":"0", "free_flash":"0"};
var main_notify='0';
addCfg("4g_mode", "983291000000", "Unavailable");
var ipv6_wan_ip="0:0:0:0:0:0:0:0";
(function(){
var wan_ipv6_info=ipv6_info_buf.split("/");
if(ipv6_info_buf==""||wan_ipv6_info[0]==""||wan_ipv6_info[0]=="::"){
ipv6_wan_ip="0:0:0:0:0:0:0:0";}
else{
ipv6_wan_ip=wan_ipv6_info[0].toUpperCase();}})();
