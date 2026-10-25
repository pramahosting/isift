# User manuals

The PDF manuals shown on the landing page (section "User manuals") live in `frontend/public/manuals/`.

To change one: edit `content.py` (text and screenshot names), replace screenshots in `shots/` (JPEG, about 1100 px wide), then run

    python3 build.py
    node print.js        # needs Node with Playwright

The PDFs are rewritten in `frontend/public/manuals/`. The list on the landing page is `MANUALS` in `frontend/src/Landing.tsx`.
