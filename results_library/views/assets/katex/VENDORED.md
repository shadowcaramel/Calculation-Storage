# Vendored KaTeX 0.18.4

Copied verbatim from the published `katex@0.18.4` package
(`sha256 0090b1ebccc77d1402ec95e85ee539e1da514d6cd6934156c00baf39dcb0e3aa`):

    dist/katex.min.css  -> katex.min.css
    dist/katex.min.js   -> katex.min.js
    dist/fonts/*.woff2  -> fonts/
    LICENSE             -> LICENSE

Shipped with the site rather than loaded from a CDN, because pages are opened
straight from the synced folder over `file://`, often with no network. Only the
`woff2` faces are kept: every browser that can run the script supports them, and
the other formats triple the size of the tree.

Letters, digits, and ordinary symbols are restyled in `style.css` to the same
Inter face as the surrounding page. KaTeX's own fonts stay for stretchy
delimiters and specialty alphabets (`\mathbb`, `\mathcal`, …).

Do not edit these files. To move to another release, replace the four items
above from that release's package and update the version and hash here.
