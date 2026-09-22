"""Default configuration seeded into the DB on first run. Edit later from the Configure screen."""
DEFAULT_CONFIG = {
    "llm": {
        # Bring Your Own LLM — ONE model handles every LLM task (understanding, targets, conversion, GAP assist).
        # Keys are stored here (server side) and masked on read. Leave "" for rules-only (no model).
        "profiles": [
            {"id": "azure-uk", "provider": "azure", "label": "Azure OpenAI — client tenant", "endpoint": "https://<resource>.openai.azure.com",
             "apiKey": "", "model": "gpt-4o", "apiVersion": "2024-10-21", "region": "UK South", "costIn": 2.5, "costOut": 10, "status": "untested"},
            {"id": "claude", "provider": "anthropic", "label": "Claude — PwC gateway", "endpoint": "https://api.anthropic.com",
             "apiKey": "", "model": "claude-sonnet-4-5", "costIn": 3, "costOut": 15, "status": "untested"},
        ],
        "activeProfile": "",       # id of the single model used for all LLM tasks; "" = rules only
        "projectBots": 200,
    },
    "env_prefix": "pwc",
    "cloud_schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "connection_refs": {
        "office365": "pwc_sharedoffice365_ar", "uiflow": "pwc_shareduiflow_ar", "aibuilder": "pwc_sharedaibuilder_ar",
        "sql": "pwc_sharedsql_ar", "commondataservice": "pwc_shareddataverse_ar",
    },
    "robin_map": {
        "sap:connect": "SAP.Connect Server: {server} Client: {client} User: {user} Password: {password}",
        "sap:runtransaction": "SAP.RunTransaction TCode: {tcode}",
        "sap:settext": "SAP.SetText Id: {id} Value: {text}",
        "sap:press": "SAP.Press Id: {id}",
        "sap:gettext": "SAP.GetText Id: {id} Output: {output}",
        "excel advanced:open": "Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess Path: {path} Visible: False ReadOnly: False Instance=> ExcelInstance",
        "excel advanced:close": "Excel.CloseExcel.Close Instance: ExcelInstance",
        "excel advanced:vlookup": "# VLOOKUP → Excel.ReadFromExcel.ReadCells then Variables.RetrieveDataTableColumnIntoList — see pattern library",
        "recorder:click": "UIAutomation.Click Element: appmask['{title!}']['{control!}']",
        "recorder:capturewindow": "UIAutomation.WaitForWindow Element: appmask['{title!}'] Timeout: 30",
        "browser:launch": "WebAutomation.LaunchEdge.LaunchEdge Url: {url} WindowState: WebAutomation.BrowserWindowState.Normal Instance=> Browser",
        "pdf:extracttext": "Pdf.ExtractTextFromPDF.ExtractText PDFFile: {path} ExtractedPDFText=> PDFText",
        "csv/txt:read": "File.ReadFromCSVFile.ReadCSV CSVFile: {path} CSVTable=> CSVTable",
        "string:substring": "Text.GetSubtext Text: {text} CharacterPosition: {start} NumberOfChars: {length} Subtext=> SubText",
        "string:replace": "Text.Replace Text: {text} TextToFind: {find} ReplaceWith: {replace} Result=> Replaced",
    },
    "pad_sample": (
        "# Paste a real PAD copy/paste sample here. Open PAD, select actions, Ctrl+C, paste into Notepad.\n"
        "# The converter treats THIS as the authoritative syntax for your PAD version.\n"
        "SAP.Connect Server: $'''PRD''' Client: $'''100''' User: SAPUser Password: SAPPwd\n"
        "SAP.SetText Id: $'''wnd[0]/usr/txtBSEG-WRBTR''' Value: Amount\n"
        "SAP.Press Id: $'''wnd[0]/tbar[0]/btn[11]'''\n"
        "SAP.GetText Id: $'''wnd[0]/sbar''' Output: DocumentNumber"
    ),
}
