import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def format_khata_name(row_text):
    """Extracts and formats names like 'BIPLAB MUKHERJEE (AT)' into 'B.Mukherjee, A.T' directly from the raw row text."""
    # This regex looks specifically for letters/spaces, followed by parentheses, ignoring numbers.
    match = re.search(r'([A-Za-z\s]+)\s*\(\s*([A-Za-z0-9]+)\s*\)', row_text)
    
    if not match:
        return "Unknown"
        
    name_part, desig = match.groups()
    name_part = name_part.strip()
    parts = name_part.split()
    
    if not parts:
        return "Unknown"
        
    if len(parts) == 1:
        formatted_name = f"{parts[0].capitalize()}"
    else:
        initials = "".join([p[0].upper() + "." for p in parts[:-1]])
        surname = parts[-1].capitalize()
        formatted_name = f"{initials}{surname}"
        
    desig = desig.upper().strip()
    if desig == "AT":
        desig = "A.T"
        
    return f"{formatted_name}, {desig}"

def extract_salary_data(pdf_file):
    """Extracts data and automatically detects if the file is SSA or Non-SSA."""
    extracted_data = []
    
    with pdfplumber.open(pdf_file) as pdf:
        # --- Robust Auto-Detect SSA vs Non-SSA ---
        first_page_text = pdf.pages[0].extract_text() or ""
        # Clean the text: remove all newlines and multiple spaces, then uppercase
        clean_header_text = re.sub(r'\s+', ' ', first_page_text).upper()
        
        is_ssa = False # Default assumption
        if "NON-SSA" in clean_header_text:
            is_ssa = False
        elif "SSA" in clean_header_text:
            is_ssa = True
        else:
            st.warning(f"Could not definitively detect SSA/Non-SSA in {pdf_file.name}. Defaulting to Non-SSA logic.")
        # -----------------------------------------

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Identify valid employee rows by checking if the first column is a Serial Number
                    if row and row[0] and str(row[0]).strip().isdigit():
                        row_text = " ".join([str(cell).replace('\n', ' ').strip() for cell in row if cell is not None])
                        tokens = row_text.split()
                        
                        try:
                            # Anchor point: Gross salary always ends in '.00' in i-OSMS
                            gross_idx = next(i for i, t in enumerate(tokens) if re.match(r'^\d+\.00$', t))
                        except StopIteration:
                            continue 
                            
                        try:
                            # Safely extract and format Name
                            name_str = format_khata_name(row_text)
                            
                            # Navigate backward from Gross Amount for allowances
                            basic = tokens[gross_idx - 10]
                            da = tokens[gross_idx - 7]
                            hra = tokens[gross_idx - 6]
                            ma = tokens[gross_idx - 5]
                            gross = tokens[gross_idx].replace('.00', '')
                            
                            # Navigate forward from Gross Amount for deductions
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
                                "Name": name_str,
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

uploaded_files = st.file_uploader("Upload Requisition PDFs", type="pdf", accept_multiple_files=True)

if st.button("Generate Acquittance Roll"):
    all_data = []
    
    if not uploaded_files:
        st.error("Please upload at least one Requisition PDF.")
    else:
        for file in uploaded_files:
            all_data.extend(extract_salary_data(file))
            
        if all_data:
            df = pd.DataFrame(all_data)
            
            # --- SORTING LOGIC ---
            # Master order array to ensure correct ledger hierarchy
            master_order = [
                "J.Sarkar, HM",
                "S.K.Paul, A.T",
                "B.Mondal, A.T",
                "B.Das, A.T",
                "B.Biswas, A.T",
                "S.Mallick, A.T",
                "B.Mukherjee, A.T",
                "P.Mondal, A.T",
                "A.Biswas, A.T",
                "S.N.Roy, A.T",
                "S.Ghosh, A.T",
                "S.Konar, A.T",
                "P.Konar, CLERK"
            ]
            
            def get_rank(name):
                try:
                    return master_order.index(name)
                except ValueError:
                    return 999 # Unlisted names drop to the bottom
            
            # Apply sorting and rebuild index
            df['Rank'] = df['Name'].apply(get_rank)
            df = df.sort_values(by='Rank').drop(columns=['Rank']).reset_index(drop=True)
            # ---------------------

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
