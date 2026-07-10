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
    match = re.match(r"(.*?)\s*\((.*?)\)", clean_name)
    
    if not match:
        return clean_name
        
    name_part, desig = match.groups()
    parts = name_part.split()
    
    if len(parts) == 1:
        formatted_name = f"{parts[0].capitalize()}"
    else:
        initials = "".join([p[0].upper() + "." for p in parts[:-1]])
        surname = parts[-1].capitalize()
        formatted_name = f"{initials}{surname}"
        
    # Format designation to match ledger (e.g., AT -> A.T)
    desig = desig.upper()
    if desig == "AT":
        desig = "A.T"
        
    return f"{formatted_name}, {desig}"

def extract_salary_data(pdf_file):
    """Extracts relevant ledger data from the i-OSMS PDF using pdfplumber."""
    extracted_data = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Identify valid employee rows by checking if the first column is a Serial Number
                    if row and row[0] and str(row[0]).strip().isdigit():
                        # Clean newlines from cells
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else '0' for cell in row]
                        
                        try:
                            # Note: i-OSMS table indices might need slight adjustment depending on cell merges.
                            # These indices are mapped to the standard output provided.
                            emp_data = {
                                "Name": format_khata_name(clean_row[1]),
                                "Basic": clean_row[6].split()[-1] if len(clean_row)>6 else '0', 
                                "DA": clean_row[8].split()[0] if len(clean_row)>8 else '0',
                                "HRA": clean_row[8].split()[1] if len(clean_row)>8 and len(clean_row[8].split())>1 else '0',
                                "MA": clean_row[9] if len(clean_row)>9 else '0',
                                "Gross": clean_row[13] if len(clean_row)>13 else '0',
                                "GPF": clean_row[14] if len(clean_row)>14 else '0',
                                "PTax": clean_row[15].split()[1] if len(clean_row)>15 and len(clean_row[15].split())>1 else '0',
                                "ITax": clean_row[15].split()[2] if len(clean_row)>15 and len(clean_row[15].split())>2 else '0',
                                "Net": clean_row[16] if len(clean_row)>16 else '0'
                            }
                            extracted_data.append(emp_data)
                        except IndexError:
                            continue # Skip malformed rows
                            
    return extracted_data

def generate_acquittance_pdf(df):
    """Generates a 1-page A4 PDF using ReportLab."""
    buffer = BytesIO()
    # Use A4 Portrait with narrow margins to fit the khata style
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15, leftMargin=15, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title = Paragraph("<b>ACQUITTANCE ROLL OF TEACHERS / NON TEACHING STAFF</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Define Table Headers
    table_data = [[
        "Sl\nNo.", "Name", "Basic\nPay", "D.A", "H.R.A", "M.A", 
        "Gross\nAmount", "G.P.F", "Prof.\nTax", "Income\nTax", "Net Amount\nPayable", "Signature"
    ]]
    
    # Append Data Rows
    for idx, row in df.iterrows():
        table_data.append([
            str(idx + 1),
            row['Name'],
            row['Basic'],
            row['DA'],
            row['HRA'],
            row['MA'],
            row['Gross'],
            row['GPF'],
            row['PTax'],
            row['ITax'],
            row['Net'],
            "" # Empty column for physical stamps/signatures
        ])
        
    # Set specific column widths to force fit onto one A4 portrait page
    col_widths = [25, 95, 45, 40, 40, 35, 55, 40, 35, 45, 60, 60]
    
    pdf_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Style the table to look like the ledger
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'), # Align names to the left
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white])
    ])
    
    # Increase row height to mimic the spacing in the physical khata
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
st.write("Upload the monthly SSA and Non-SSA Salary Requisition PDFs to generate a consolidated A4 ledger.")

col1, col2 = st.columns(2)
with col1:
    ssa_file = st.file_uploader("Upload SSA PDF", type="pdf")
with col2:
    non_ssa_file = st.file_uploader("Upload Non-SSA PDF", type="pdf")

if st.button("Generate Acquittance Roll"):
    all_data = []
    
    if ssa_file:
        all_data.extend(extract_salary_data(ssa_file))
    if non_ssa_file:
        all_data.extend(extract_salary_data(non_ssa_file))
        
    if not all_data:
        st.error("Please upload at least one valid Requisition PDF.")
    else:
        df = pd.DataFrame(all_data)
        
        # Display the parsed data on screen for verification
        st.subheader("Data Preview")
        st.dataframe(df, use_container_width=True)
        
        # Generate the PDF
        pdf_buffer = generate_acquittance_pdf(df)
        
        st.success("PDF Generated Successfully!")
        st.download_button(
            label="Download A4 Acquittance PDF",
            data=pdf_buffer,
            file_name="Acquittance_Roll.pdf",
            mime="application/pdf"
        )