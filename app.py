import json

# ==============================================================================
# GOOGLE SHEETS CONNECTOR
# ==============================================================================
def connect_to_google_sheet(sheet_name="COA Master Log"):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    if "gcp_service_account" in st.secrets:
        # Convert dictionary from st.secrets into a proper dictionary format for oauth2client
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "credentials.json", scope
        )

    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    return sheet
