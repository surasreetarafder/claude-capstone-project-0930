# Creates the QA test documents (quality_manual.txt and a 2-page quality_manual.pdf).
# Run:  py tests/make_docs.py
import os, textwrap
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # write files next to this script
paras = [
 "Section 1 - Deviation Management. Any deviation from an approved procedure must be reported to Quality Assurance within 24 hours of detection. The deviation owner records the event in the electronic quality system and assigns an initial risk category of minor, major or critical.",
 "Section 2 - CAPA. Corrective and preventive actions (CAPA) must be opened for every major or critical deviation. Each CAPA must be closed within 30 calendar days unless an extension is approved by the Head of Quality. Effectiveness checks are performed 90 days after closure.",
 "Section 3 - Batch Record Retention. Executed batch manufacturing records are retained for 7 years after the expiry date of the batch. Records are stored in the secure document archive in Building C and scanned copies are kept in the validated electronic archive.",
 "Section 4 - Cleanroom Environment. Grade B cleanrooms are maintained at a temperature of 18 to 22 degrees Celsius and a relative humidity of 30 to 60 percent. Environmental monitoring results outside these limits must be escalated to the production supervisor immediately.",
 "Section 5 - Change Control. All changes to validated equipment, processes or computerized systems require a formal change request. Change requests are approved by the Change Control Board, which is chaired by the Head of Quality Assurance.",
 "Section 6 - Annual Product Quality Review. An annual product quality review (APQR) is prepared for every commercial product. The APQR must be completed and approved by 31 March of the following year and is presented to senior management.",
 "Section 7 - Training. All GMP staff complete annual GMP refresher training. New employees must complete induction training before performing any GMP activity without supervision. Training records are maintained in the learning management system.",
 "Section 8 - Supplier Qualification. Suppliers of starting materials are qualified through a questionnaire, a quality agreement and an on-site audit. Approved suppliers are re-audited every 3 years, or sooner if significant quality issues occur.",
]
filler = " This section applies to all HelixNova Pharma manufacturing and packaging sites and to contractors working on their behalf. The document owner reviews this section every two years as part of the periodic review of the quality management system, and any questions about it should be raised with the local Quality Assurance representative."
paras = [p + filler for p in paras]
text = "HelixNova Pharma - Quality Manual QM-001\n\n" + "\n\n".join(paras) + "\n"
open("quality_manual.txt", "w", encoding="utf-8").write(text)

# Build a real 2-page text PDF by hand (no extra libraries needed).
lines = []
for p in text.split("\n"):
    lines += textwrap.wrap(p, 90) or [""]
pages = [lines[:45], lines[45:]]
def esc(s): return s.replace("\\", "\\\\").replace("(", "\(").replace(")", "\)")
objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
kids = []
for pl in pages:
    stream = "BT /F1 10 Tf 14 TL 50 780 Td " + " ".join(f"({esc(l)}) Tj T*" for l in pl) + " ET"
    objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
    kids.append(f"{len(objs)} 0 R")
objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
out, offs = b"%PDF-1.4\n", []
for i, o in enumerate(objs, 1):
    offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
x = len(out)
out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
open("quality_manual.pdf", "wb").write(out)
print("TXT chars:", len(text), "| PDF bytes:", len(out), "| PDF pages:", len(pages))
