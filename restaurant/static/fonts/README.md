# Customer menu fonts

- `Forum-Regular.ttf`: Denis Masharov, SIL Open Font License 1.1. Restored without modification from this repository's commit `2ed5307`; the complete license is in `Forum-OFL.txt`. Used for menu category headings, dish names and prices.
- Satoshi Light (300): Indian Type Foundry / Fontshare. Used for menu descriptions. The guest template loads the publisher's WOFF2 URL from `https://api.fontshare.com/v2/css?f[]=satoshi@300&display=swap`. For offline development, obtain the official WOFF2 and place it here as `Satoshi-Light.local.woff2`. Git ignores that file. The guest page uses the local copy when present, otherwise the CDN and the existing system sans-serif fallback.

Sources: [Satoshi](https://www.fontshare.com/fonts/satoshi), [Fontshare licensing](https://www.fontshare.com/licenses). The official download's ITF Free Font License 2.0 permits web use and self-hosting, but restricts redistribution through repositories; use the publisher CDN here.

The menu follows the inspected Qitchen reference: Forum 20px/24px, 1px letter spacing, uppercase dish names; same-size Forum prices; Satoshi Light 14px/22.4px descriptions. The narrower mobile layout reduces names and prices together to 18px.
