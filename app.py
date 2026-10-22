import re
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import pdfplumber
import streamlit as st


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def fix_potency_decimal(val):
    """
    Ensures potency percentages have correct decimal placement:
    - '1244%' -> '1.244%'
    - '25555%' -> '25.555%'
    - '23978%' -> '23.978%'
    """
    if not val or val in ["N/A", "ND", "<LOQ", "<LOQ%"]:
        return val

    # Match raw digits and optional percent symbol
    match = re.search(r"^(\d+)\s*(%)?$", val.strip())
    if match:
        digits = match.group(1)
        has_pct = "%" if match.group(2) or "%" in val else ""

        # If decimal is missing and raw integer represents >100% potency
        if not "." in val:
            if len(digits) == 5:
                # e.g., 25555 -> 25.555
                return f"{digits[:2]}.{digits[2:]}{has_pct}"
            elif len(digits) == 4:
                # Check leading digit: if 1-9 without leading high numbers
                # e.g., 1244 -> 1.244 or 2397 -> 23.97
                if int(digits[:2]) > 35:  # Potency unlikely over 35%
                    return f"{digits[:1]}.{digits[1:]}{has_pct}"
                else:
                    return f"{digits[:2]}.{digits[2:]}{has_pct}"
            elif len(digits) == 3:
                # e.g., 124 -> 1.24% or 12.4%
                if int(digits[:2]) > 35:
                    return f"{digits[:1]}.{digits[1:]}{has_pct}"
                else:
                    return f"{digits[:2]}.{digits[2:]}{has_pct}"

    return val


# ==============================================================================
# GOOGLE SHEETS CONNECTOR
# ==============================================================================
def connect_to_google_sheet(sheet_name="COA Master Log"):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace(
                "\\n", "\n"
            )
        creds = Credentials.from_service_account_info(
            creds_dict, scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file(
            "credentials.json", scopes=scopes
        )

    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    return sheet


# ==============================================================================
# LAB PARSERS
# ==============================================================================
def parse_gva(text):
    def parse_regex(pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "N/A"

    def get_compound(compound_name):
        pattern = rf"{compound_name}\b.*?(ND|<LOQ|[\d.]+\s*%|[\d.]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_val = match.group(1).strip()
            if raw_val in ["ND", "<LOQ"]:
                return raw_val

            if "%" not in raw_val:
                raw_val = f"{raw_val}%"

            return fix_potency_decimal(raw_val)
        return "ND"

    overall_status = "PASS" if "PASS" in text else "FAIL"

    return {
        "Creation Date": parse_regex(r"Date Released:\s*([\d/]+)"),
        "Sample Product Description": parse_regex(
            r"(?:Report #|Sample Description):\s*\d*\s*\n*(.*?)\n*(?:Sample #|METRC)"
        ).replace("\n", " "),
        "Parent METRC ID": parse_regex(
            r"METRC Source Package ID:\s*([A-Z0-9]+)"
        ),
        "PASS / FAIL": overall_status,
        "Production Batch #": parse_regex(r"METRC Batch ID:\s*([\w-]+)"),
        "FINAL RESULT?": "Final",
        "LAB": "Green Valley Analytics",
        "Net Wt. (g)": parse_regex(r"Weight:\s*([\d.]+g?)"),
        "Testing Code": "N/A",
        "Storage Code": "N/A",
        "Target Serving (g)": "N/A",
        "Gross Wt. (g)": "N/A",
        "Date Sent": parse_regex(r"Date Collected:\s*([\d/]+)"),
        "Date Received": parse_regex(r"Date Received:\s*([\d/]+)"),
        "Sample METRC ID": parse_regex(r"METRC Sample ID:\s*([A-Z0-9]+)"),
        "METRC Manifest": "N/A",
        "Lab Manifest": "N/A",
        "Testing COA Link": "N/A",
        "RETEST Batch? (Y/N)": "N/A",
        "Is this a RETEST (Y/N)": "N/A",
        "Reason for Failure": "N/A",
        "TAC": fix_potency_decimal(
            parse_regex(r"Total Cannabinoids\s*[:|]?\s*([\d.]+\s*%?)")
        ),
        "THC": fix_potency_decimal(
            parse_regex(r"Total THC\s*[:|]?\s*([\d.]+\s*%?)")
        ),
        "CBD": fix_potency_decimal(
            parse_regex(r"Total CBD\s*[:|]?\s*([\d.]+\s*%?)")
        ),
        "THCa": get_compound("THCa"),
        "CBDa": get_compound("CBDa"),
        "Terp": fix_potency_decimal(
            parse_regex(r"Total Terpenes\s*[:|]?\s*([\d.]+\s*%?)")
        ),
        "Additional Notes": "N/A",
        "CBGA": get_compound("CBGA"),
        "Reference Number": parse_regex(r"Sample #:\s*(\d+)"),
    }


def parse_g7(text):
    def parse_regex(pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "N/A"

    def get_compound(compound_name):
        match = re.search(
            rf"[\★\*]?\s*{compound_name}\s*[\|:]?\s*([<LOQND\d\.]+\s*(?:Wt\.%)?)",
            text,
            re.IGNORECASE,
        )
        return (
            fix_potency_decimal(match.group(1).strip())
            if match
            else "<LOQ Wt.%"
        )

    overall_status = (
        "FAIL"
        if re.search(r"Microbiology\s*\|\s*Fail", text, re.IGNORECASE)
        else "PASS"
    )

    return {
        "Creation Date": parse_regex(r"Date Reported\s*[\|:]?\s*([\d-]+\s*[\d:]+)"),
        "Sample Product Description": parse_regex(
            r"COC Client SID\s*[\|:]?\s*\w+:\s*(.*)"
