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

    match = re.search(r"^(\d+)\s*(%)?$", val.strip())
    if match:
        digits = match.group(1)
        has_pct = "%" if match.group(2) or "%" in val else ""

        if not "." in val:
            if len(digits) == 5:
                return f"{digits[:2]}.{digits[2:]}{has_pct}"
            elif len(digits) == 4:
                if int(digits[:2]) > 35:
                    return f"{digits[:1]}.{digits[1:]}{has_pct}"
                else:
                    return f"{digits[:2]}.{digits[2:]}{has_pct}"
            elif len(digits) == 3:
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
        ),
        "Parent METRC ID": parse_regex(r"Client Batch ID\s*[\|:]?\s*([A-Z0-9]+)"),
        "PASS / FAIL": overall_status,
        "Production Batch #": parse_regex(r"COC Client BID\s*[\|:]?\s*([\w-]+)"),
        "FINAL RESULT?": "Final",
        "LAB": "G7 Lab, LLC",
        "Net Wt. (g)": "N/A",
        "Testing Code": "N/A",
        "Storage Code": "N/A",
        "Target Serving (g)": "N/A",
        "Gross Wt. (g)": "N/A",
        "Date Sent": "N/A",
        "Date Received": parse_regex(r"Date Received\s*[\|:]?\s*([\d-]+\s*[\d:]+)"),
        "Sample METRC ID": parse_regex(r"Metrc Tag\s*[\|:]?\s*([A-Z0-9]+)"),
        "METRC Manifest": "N/A",
        "Lab Manifest": "N/A",
        "Testing COA Link": "N/A",
        "RETEST Batch? (Y/N)": "N/A",
        "Is this a RETEST (Y/N)": "N/A",
        "Reason for Failure": (
            "Microbiology Failure (Total Yeast & Mold)"
            if overall_status == "FAIL"
            else "N/A"
        ),
        "TAC": fix_potency_decimal(
            parse_regex(r"Total Potency\s*[\|:]?\s*([\d.]+\s*(?:Wt\.%)?)")
        ),
        "THC": fix_potency_decimal(
            parse_regex(
                r"Total THC\s*-\s*THC\+THCAX0\.877\s*[\|:]?\s*([\d.]+\s*(?:Wt\.%)?)"
            )
        ),
        "CBD": fix_potency_decimal(
            parse_regex(
                r"Total CBD\s*CBD\+CBDAX0\.877\s*[\|:]?\s*([\d.]+\s*(?:Wt\.%)?)"
            )
        ),
        "THCa": get_compound("Delta 9 THCA"),
        "CBDa": get_compound("CBDA"),
        "Terp": fix_potency_decimal(
            parse_regex(r"Total Terpenes\s*[\|:]?\s*([\d.]+\s*(?:Wt\.%)?)")
        ),
        "Additional Notes": "N/A",
        "CBGA": get_compound("CBGA"),
        "Reference Number": parse_regex(r"Sample ID\s*[\|:]?\s*([\w-]+)"),
    }


def process_pdf(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])

    if "Green Valley" in full_text or "gvalabs.com" in full_text:
        return parse_gva(full_text)
    elif "G7 Lab" in full_text or "g7lab.com" in full_text:
        return parse_g7(full_text)
    else:
        return {"LAB": "Unregistered Vendor"}


# ==============================================================================
# STREAMLIT PORTAL UI
# ==============================================================================
st.set_page_config(page_title="COA to Google Sheets Portal", layout="wide")
st.title("🧪 COA Data Portal -> Google Sheets")

uploaded_files = st.file_uploader(
    "Drop COA PDFs here", type=["pdf"], accept_multiple_files=True
)

if uploaded_files:
    results = [process_pdf(file) for file in uploaded_files]
    df = pd.DataFrame(results)

    st.subheader("Preview Extracted Records")
    st.dataframe(df)

    if st.button("🚀 Push All Records to Google Sheets"):
        try:
            sheet = connect_to_google_sheet("COA Master Log")
            for record in results:
                sheet.append_row(list(record.values()))
            st.success(
                f"Successfully appended {len(results)} record(s) to Google Sheets!"
            )
        except Exception as e:
            st.error(f"Error writing to Google Sheets: {e}")
