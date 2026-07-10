import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def format_khata_name(full_name):
    """Converts 'JOYDIP SARKAR (HM)' to 'J.Sarkar, HM'"""
    clean_name = str(full_name).replace('\n', ' ').strip()
    match = re.search(r'([A-Z\s]+)\s*\(([A-Z0-9]+)\)', clean_name)
    
    if not match:
        return clean_name
        
    name_part, desig = match.groups()
    parts = name_part.strip().split()
    
    if len(parts) == 1:
        formatted_name = f"{parts[0].capitalize()}"
    else:
        initials = "".join([p[0].upper() + "." for p in parts[:-1]])
        surname = parts[-1].capitalize()
        formatted_name = f"{initials}{surname}"
        
    desig = desig.upper()
    if desig == "AT":
        desig = "A.T"
        
    return f"{formatted_name}, {desig}"

def extract_salary_data(pdf_file):
    """Extracts data and automatically detects if the file is SSA or Non-SSA."""
    extracted_data = []
    
    with pdfplumber.open(pdf_file) as pdf:
        # --- Auto-Detect SSA vs Non-SSA ---
        first_page_text = pdf.pages[0].extract_text()
        is_ssa = False # Default assumption
        
        if "(NON-SSA SCHOOL)" in first_page_text:
            is_ssa = False
        elif "(SSA SCHOOL)" in first_page_text:
            is_ssa = True
        else:
            st.warning(f"Could not definitively detect SSA/Non-SSA in {pdf_file.name}. Defaulting to Non-SSA logic.")
        # ----------------------------------

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and row[0] and str(row[0]).strip().isdigit():
                        row_text = " ".join([str(cell).replace('\n', ' ').strip() for cell in row if cell is not None])
                        tokens = row_text.split()
                        
                        try:
                            # Anchor point: Gross salary always ends in '.00' in i-OSMS
                            gross_idx = next(i for i, t in enumerate(tokens) if re.match(r'^\d+\.00$', t))
                        except StopIteration:
                            continue 
                            
                        try:
                            name_match = re.search(r'([A-Z\s]+)\s*\(([A-Z0-9]+)\)', row_text)
                            raw_name = name_match.group(0) if name_match else "Unknown"
                            
                            basic = tokens[gross_idx - 10]
                            da = tokens[gross_idx - 7]
                            hra = tokens[gross_idx - 6]
                            ma = tokens[gross_idx - 5]
                            gross = tokens[gross_idx].replace('.00', '')
                            
                            gpf = tokens[gross_idx + 1]
                            net = tokens[-1] 
                            
                            # Apply the correct tax logic based on auto-detection
                            if is_ssa:
                                ptax = tokens[gross_idx + 2]
                                itax = tokens[gross_idx + 3]
                            else:
                                ptax = tokens[gross_idx + 4]
                                itax = tokens[gross_idx + 5]
                                
                            extracted_data.append({
                                "Name": format_khata_name(raw_name),
                                "Basic": basic,
                                "DA": da,
                                "HRA": hra,
                                "MA": ma,
                                "Gross": gross,
                                "GPF": gpf,
                                "PTax": ptax,
                                "ITax": itax,
                                "Net": net
                            })
                        except IndexError:
                            continue 
                            
    return extracted_data

def generate_acquittance_pdf(df):
    """Generates a 1-page A4 PDF using ReportLab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15, leftMargin=15, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title = Paragraph("<b>ACQUITTANCE ROLL OF TEACHERS / NON TEACHING STAFF</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    table_data = [[
        "Sl\nNo.", "Name", "Basic\nPay", "D.A", "H.R.A", "M.A", 
        "Gross\nAmount", "G.P.F", "Prof.\nTax", "Income\nTax", "Net Amount\nPayable", "Signature"
    ]]
    
    for idx, row in df.iterrows():
        table_data.append([
            str(idx + 1), row['Name'], row['Basic'], row['DA'], row['HRA'], row['MA'],
            row['Gross'], row['GPF'], row['PTax'], row['ITax'], row['Net'], ""
        ])
        
    col_widths = [25, 95, 45, 40, 40, 35, 55, 40, 35, 45, 60, 60]
    pdf_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white])
    ])
    
    for i in range(1, len(table_data)):
        style.add('BOTTOMPADDING', (0, i), (-1, i), 15)
        style.add('TOPPADDING', (0, i), (-1, i), 15)
        
    pdf_table.setStyle(style)
    elements.append(pdf_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- Streamlit UI ---
st.set_page_config(page_title="Acquittance Roll Generator", layout="centered")

st.title("Acquittance Roll Generator")
st.write("Upload your i-OSMS Salary Requisition PDFs. The system will automatically detect SSA/Non-SSA formatting.")

if "pdf_buffer" not in st.session_state:
    st.session_state.pdf_buffer = None
if "df_preview" not in st.session_state:
    st.session_state.df_preview = None

# Single uploader that accepts multiple files
uploaded_files = st.file_uploader("Upload Requisition PDFs", type="pdf", accept_multiple_files=True)

if st.button("Generate Acquittance Roll"):
    all_data = []
    
    if not uploaded_files:
        st.error("Please upload at least one Requisition PDF.")
    else:
        # Loop through all uploaded files and let the script figure out what they are
        for file in uploaded_files:
            all_data.extend(extract_salary_data(file))
            
        if all_data:
            df = pd.DataFrame(all_data)
            st.session_state.df_preview = df
            st.session_state.pdf_buffer = generate_acquittance_pdf(df)
            st.success("PDF Generated Successfully!")

if st.session_state.df_preview is not None:
    st.subheader("Data Preview")
    st.dataframe(st.session_state.df_preview, use_container_width=True)

if st.session_state.pdf_buffer is not None:
    st.download_button(
        label="Download A4 Acquittance PDF",
        data=st.session_state.pdf_buffer,
        file_name="Acquittance_Roll.pdf",
        mime="application/pdf"
    )
