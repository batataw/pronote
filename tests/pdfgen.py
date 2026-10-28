"""Générateur de PDF minimal (texte Helvetica + rectangles) pour fabriquer des emplois du temps
synthétiques dans les tests. Coordonnées en « top » (depuis le haut), comme pdfplumber."""

W, H = 842, 595


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_stream(ops):
    out = []
    for op in ops:
        if op[0] == "rect":
            _, x0, top, x1, bottom = op
            out.append(f"{x0} {H - bottom} {x1 - x0} {bottom - top} re S")
        else:
            _, x, top, text, size = op
            out.append(f"BT /F1 {size} Tf {x} {H - top - size * 0.75} Td ({_esc(text)}) Tj ET")
    return "\n".join(out).encode("latin-1")


def make_pdf(pages):
    """`pages` : liste de listes d'opérations ("rect", x0, top, x1, bottom) | ("text", x, top, texte, taille)."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    kids = []
    for i, ops in enumerate(pages):
        pid, cid = 4 + 2 * i, 5 + 2 * i
        stream = page_stream(ops)
        objs[cid] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objs[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] "
                     f"/Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>").encode()
        kids.append(f"{pid} 0 R")
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += b"%d 0 obj\n" % n + objs[n] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % offsets[n] for n in sorted(objs))
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def timetable(days, labels, cells, title="LYCEE TEST"):
    """Grille type PRONOTE : `labels` = libellés de l'axe, une ligne de 40 pt par intervalle ;
    `cells` = (index jour, ligne début, ligne fin (exclue), [lignes de texte])."""
    gx, gy, cw, rh = 70, 80, 120, 40
    ops = [("text", 20, 20, title, 10),
           ("rect", gx, gy, gx + cw * len(days), gy + rh * (len(labels) - 1))]
    for i, d in enumerate(days):
        ops.append(("text", gx + cw * i + cw / 2 - 15, gy - 15, d, 9))
    for k, t in enumerate(labels):
        ops.append(("text", 30, gy + rh * k - 3, t, 7))
    for d, r0, r1, lines in cells:
        x0, top = gx + cw * d + 1, gy + rh * r0 + 1
        ops.append(("rect", x0, top, x0 + cw - 2, gy + rh * r1 - 1))
        for j, line in enumerate(lines):
            ops.append(("text", x0 + 5, top + 4 + 9 * j, line, 7))
    return ops
