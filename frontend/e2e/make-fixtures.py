"""Generate the synthetic upload fixtures used by the Playwright specs (no real documents).

Run from the repository root with the backend venv (Pillow is a backend dependency):
    backend/.venv/Scripts/python frontend/e2e/make-fixtures.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "fixtures"

FIXTURES = {
    "id-front.png": ((860, 540), "#dfe9f5", "TEST ID CARD - FRONT"),
    "id-back.png": ((860, 540), "#e8eef0", "TEST ID CARD - BACK"),
    "syndicate-card.png": ((860, 540), "#f3ecd8", "TEST SYNDICATE CARD"),
    "spouse-id.png": ((860, 540), "#e5f0e8", "TEST SPOUSE ID"),
    "marriage.png": ((800, 1000), "#f5f1e6", "TEST MARRIAGE CERTIFICATE"),
    "insurance.png": ((800, 1000), "#eef1f6", "TEST INSURANCE PRINT"),
    "birth-son.png": ((800, 1000), "#f6eef0", "TEST BIRTH CERTIFICATE (SON)"),
    "birth-daughter.png": ((800, 1000), "#f0eef6", "TEST BIRTH CERTIFICATE (DAUGHTER)"),
    "receipt.png": ((900, 640), "#fffbe8", "TEST PAYMENT RECEIPT"),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, (size, colour, label) in FIXTURES.items():
        image = Image.new("RGB", size, colour)
        draw = ImageDraw.Draw(image)
        draw.rectangle([12, 12, size[0] - 12, size[1] - 12], outline="#1a1a2e", width=4)
        draw.text((40, 40), label, fill="#1a1a2e")
        draw.text((40, 70), "Synthetic fixture - not a real document", fill="#4a5568")
        image.save(OUT / name, optimize=True)
        print(name, size)


if __name__ == "__main__":
    main()
