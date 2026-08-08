import re
import socket
import requests
from typing import Dict, Any
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from core.db_functions import init_db, search_db

# ---------------------------------------------------------------------------
# Detailed Scan — passive/OSINT modules for a single IP.
#
# Each module is a plain function: (ip: str) -> dict. Register it with
# @register_detail_module("Display Name") and it automatically:
#   - runs in the "DETAILED SCAN" tab when the user clicks Run Analysis
#   - shows up as its own card in the results view
#
# ---------------------------------------------------------------------------

DETAILED_SCAN_MODULES = []


def register_detail_module(name):
    def decorator(fn):
        DETAILED_SCAN_MODULES.append((name, fn))
        return fn
    return decorator


@register_detail_module("Reverse DNS")
def mod_reverse_dns(ip):
    try:
        hostname, aliases, _ = socket.gethostbyaddr(ip)
        return {"hostname": hostname, "aliases": aliases}
    except Exception as e:
        return {"error": str(e)}


@register_detail_module("WHOIS (whois.com)")
def mod_whois(ip):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }
        r = requests.get(f"https://www.whois.com/whois/{ip}", headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")

        pre_tag = soup.find("pre", {"class": "df-raw", "id": "registryData"})

        if pre_tag:
            data = {}
            temp = pre_tag.get_text().split("\n")
            for i in temp:
                data[i.split(": ")[0]] = i.split(": ")[1].strip() if len(i.split(": ")) > 1 else ''
            return data

        blocks = soup.find_all("div", class_="df-block")
        if blocks:
            data = {}
            for block in blocks:
                heading_tag = block.find("div", class_="df-heading")
                section = heading_tag.get_text(strip=True) if heading_tag else "Info"
                for row in block.find_all("div", class_="df-row"):
                    label_tag = row.find("div", class_="df-label")
                    value_tag = row.find("div", class_="df-value")
                    if label_tag and value_tag:
                        label = label_tag.get_text(strip=True).rstrip(":")
                        value = value_tag.get_text(separator="\n", strip=True)
                        data[f"{section} — {label}"] = value
            if data:
                return data


        whois_section = soup.find("div", class_="whois-data")
        if whois_section:
            data = {}
            for row in whois_section.find_all("div", class_="df-row"):
                label_tag = row.find("div", class_="df-label")
                value_tag = row.find("div", class_="df-value")
                if label_tag and value_tag:
                    label = label_tag.get_text(strip=True).rstrip(":")
                    value = value_tag.get_text(separator="\n", strip=True)
                    data[label] = value
            if data:
                return data

        return {"error": "could not find whois data on page (layout may have "
                          "changed, or no record for this query)"}
    except Exception as e:
        return {"error": str(e)}


@register_detail_module("IP-API")
def mod_ipapi(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=6)
        d = r.json()
        if d.get("status") != "success":
            return {"error": d.get("message", "lookup failed")}
        return {
            "country": d.get("country"), "region": d.get("regionName"),
            "city": d.get("city"), "isp": d.get("isp"), "org": d.get("org"),
            "link" : f"https://www.google.com/maps/place/{d.get("lat")},{d.get("lon")}/@{d.get("lat")},{d.get("lon")},16z",
        }
    except Exception as e:
        return {"error": str(e)}


@register_detail_module("Local DB")
def mod_local_db(ip):
    try:
        conn = init_db()
        res = search_db(conn, ip)
        data = {}
        for i, port in enumerate(res):
            data[f"{i} Open"] = f"{port[1]}/{port[2]}"
        return data
    except Exception as e:
        return {"error": str(e)}


@register_detail_module("Wayback URLs")
def mod_waybackurls(host, subs=True, timeout=60):
    pattern = f"*.{host}/*" if subs else f"{host}/*"

    params = {"url": pattern, "output": "json", "fl": "original", "collapse": "urlkey"}

    result = {"success": False, "host": host, "count": 0, "urls": [], "error": None}

    try:
        resp = requests.get("http://web.archive.org/cdx/search/cdx", params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        result["error"] = str(e)
        return result

    if not data or len(data) < 2:
        result["success"] = True
        return result

    urls = sorted({row[0] for row in data[1:] if row})

    result["success"] = True
    result["count"] = len(urls)
    result["urls"] = urls
    return result


class AzureTargetAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def get_initial_info(self, email):
        domain = email.split('@')[-1]
        info = {
            "target_email": email,
            "target_domain": domain,
            "tenant_id": None,
            "namespace_type": None,
            "openid_config": None 
        }

        realm_url = f"https://login.microsoftonline.com/common/userrealm/{email}?api-version=2.1"
        try:
            realm_data = self.session.get(realm_url).json()
            info["namespace_type"] = realm_data.get("NameSpaceType")
        except: pass

        openid_url = f"https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration"
        try:
            res = self.session.get(openid_url)
            if res.status_code == 200:
                oid_data = res.json()
                info["openid_config"] = oid_data 
                
                if "token_endpoint" in oid_data:
                    info["tenant_id"] = oid_data["token_endpoint"].split('/')[3]
                    info["region"] = oid_data.get("tenant_region_scope")
        except: pass

        return info

    def deep_scan(self, info):
        tenant_id = info.get("tenant_id")
        if not tenant_id:
            return {"error": "Tenant ID not found, deep scan aborted."}


        branding_url = "https://login.microsoftonline.com/common/GetCredentialType"
        payload = {"username": info["target_email"], "isOtherIdpSupported": True, "check_one_tap": True}
        
        security = {}
        try:
            res = self.session.post(branding_url, json=payload).json()
            security["organization_name"] = res.get("DisplayName")
            security["mfa_status"] = "Active (FIDO/MFA)" if res.get("IsFidoSupported") else "Standard/Not Forced"
            security["guest_invites"] = "Allowed" if res.get("IfExistsResult") == 1 else "Restricted"
        except: pass

        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
        params = {
            "client_id": "00000003-0000-0000-c000-000000000000",
            "response_type": "code",
            "scope": "openid",
            "domain_hint": "gmail.com"
        }
        b2b_status = "Unknown"
        try:
            res = self.session.get(auth_url, params=params, allow_redirects=False)
            b2b_status = "Enabled" if "error" not in res.headers.get("Location", "") else "Restricted"
        except: pass

        return {
            "organization": security.get("organization_name"),
            "security_policy": {
                "mfa_at_login": security.get("mfa_status"),
                "can_invite_guests": security.get("guest_invites"),
                "b2b_potential": b2b_status
            }
        }

    def run(self, email):
        print(f"[*] Starting OSINT flow for: {email}")
        
        base_info = self.get_initial_info(email)
        deep_info = self.deep_scan(base_info)
        
        final_report = {
            "target": base_info["target_email"],
            "infrastructure": {
                "domain": base_info["target_domain"],
                "tenant_id": base_info["tenant_id"],
                "type": base_info["namespace_type"],
                "region": base_info.get("region"),
                "raw_openid_config": base_info["openid_config"]
            },
            "analysis": deep_info
        }
        return final_report


@register_detail_module("Tenant")
def mod_tenant(domain):
    pattern = r'^(?:\d{1,3}\.){3}\d{1,3}$'
    if bool(re.fullmatch(pattern, domain)):
        return {"error": "input is not a domain name"}

    try:   
        analyzer = AzureTargetAnalyzer()
        target_email = "test@" + domain
        data = analyzer.run(target_email)
        return data
    except Exception as e:
        return {"error": str(e)}
