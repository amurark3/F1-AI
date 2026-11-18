"""Parsers for the FIA's event documents, one module per kind (see :mod:`..kinds`).

Each takes a document's extracted text (and title where the title carries a
fact) and returns frozen dataclasses, or raises
:class:`~app.data.fia_documents.text.DocumentParseError` when the text does
not have the shape its kind promises. Rows are keyed by car number: the PDFs
run a driver's name into the team's ("BEARMANTGR Haas F1 Team"), so names are
kept as printed and the car is what joins a row to the entry list.
"""
