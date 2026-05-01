# variable:template

`"type": "variable:template"` composes multiple namespace variables into a single output string using a Jinja2 template. It is the multi-variable form of [`variable`](./lookup.md).

Only valid in `emitter.dimensions`.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `variable:template` |
| `name` | Yes | Output field name in the emitted record. |
| `template` | Yes | Jinja2 template string. Reference namespace variables directly by name: `{{ var_foo }}`. |

```json
{"name": "uri_path", "type": "variable:template", "template": "/{{ var_asset_dir }}/{{ var_asset_name }}.{{ var_asset_ext }}"}
```

Any Jinja2 expression or filter is valid:

```json
{"name": "feed_url", "type": "variable:template", "template": "/feeds/product_feed_{{ var_category }}.json"}
{"name": "label",    "type": "variable:template", "template": "{{ var_product | upper }} ({{ var_category }})"}
```

If a referenced variable is not in the namespace at emit time, the engine raises a `jinja2.UndefinedError`. The same setup-before-emit rule applies as for `variable`.

## Use with subprocess:multi:variables

`variable:template` is particularly useful in child configs where values are composed from variables injected by the parent (via `items`) combined with session-level variables set earlier in the parent's flow:

```
parent setup_session  →  var_asset_dir = "static"          (session-scoped)
parent items          →  var_asset_name, var_asset_ext      (per-iteration)
child emitter         →  uri_path = /{{ var_asset_dir }}/{{ var_asset_name }}.{{ var_asset_ext }}
```

This is effectively "calling a function with arguments" — the parent's namespace context shapes what the child emits without the child needing to know the full path in advance.

---

[← variable types](../variable.md)
