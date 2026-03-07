&amp;amp; &amp;lt;div&amp;gt; &amp;nbsp;

# Understanding HTML Entity Encoding &amp;amp; Escaping

## The &amp;lt;script&amp;gt; Problem

When HTML gets double-encoded through multiple conversion passes, you end up with artifacts like &amp;amp;amp; instead of &amp;. This article explores why.

The most common issue: content that passes through CMS → RSS feed → reader app → markdown conversion. Each layer may re-encode entities:

- `&` → `&amp;` → `&amp;amp;` → `&amp;amp;amp;`
- `<` → `&lt;` → `&amp;lt;`
- `>` → `&gt;` → `&amp;gt;`
- `"` → `&quot;` → `&amp;quot;`
- Non-breaking spaces: `&nbsp;` appearing as literal text

## Common Patterns

Here are some &amp;quot;real world&amp;quot; examples:

1. **RSS feeds**: Feed content is HTML-escaped, then the reader app HTML-escapes it again
2. **CMS migrations**: WordPress → Hugo → Astro, each escaping differently
3. **API responses**: JSON with HTML content, parsed by libraries that auto-escape

### Code Example

```html
<!-- This is what you want -->
<p>Tom &amp; Jerry</p>

<!-- This is what you get after double-encoding -->
<p>Tom &amp;amp; Jerry</p>

<!-- Triple-encoded from a bad migration -->
<p>Tom &amp;amp;amp; Jerry</p>
```

## The Fix

The general approach:

```python
import html

def fix_double_encoding(text: str, max_passes: int = 3) -> str:
    """Unescape HTML entities, handling multiple encoding layers."""
    for _ in range(max_passes):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text
```

Always limit the passes — you don't want to accidentally decode entities that are meant to be displayed as literals (like in code examples about encoding).

## Conclusion

Double-encoded HTML entities are a sign of a broken pipeline. Fix the source, not the symptoms. But when you can't fix the source, iterative `html.unescape()` is your friend.

&amp;nbsp;

---

&amp;copy; 2026 WebDev Weekly &amp;middot; All Rights Reserved

[Privacy Policy](/privacy) &amp;middot; [Terms](/terms) &amp;middot; [Contact](/contact)

Subscribe to our newsletter for more web development tips!
