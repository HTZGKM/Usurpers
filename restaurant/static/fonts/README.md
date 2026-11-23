# Customer menu fonts

- `Forum-Regular.ttf`: Denis Masharov, SIL Open Font License 1.1. Restored without modification from this repository's commit `2ed5307`; the complete license is in `Forum-OFL.txt`. Used for menu category headings, dish names and prices.
- Satoshi Light (300): Indian Type Foundry / Fontshare. Loaded from the publisher's official WOFF2 CDN URL in `guest-ember.css`, as returned by `https://api.fontshare.com/v2/css?f[]=satoshi@300&display=swap` on 2026-11-23. No Satoshi font binary is redistributed in this repository. Used only for menu descriptions, with the existing system sans-serif stack as fallback.

Sources: [Satoshi](https://www.fontshare.com/fonts/satoshi), [Fontshare licensing](https://www.fontshare.com/licenses). The official download's ITF Free Font License 2.0 permits web use and self-hosting, but restricts redistribution through repositories; use the publisher CDN here.

The menu follows the inspected Qitchen reference: Forum 20px/24px, 1px letter spacing, uppercase dish names; same-size Forum prices; Satoshi Light 14px/22.4px descriptions. The narrower mobile layout reduces names and prices together to 18px.
