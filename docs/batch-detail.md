# Per-batch detail: what was changed and which smells moved

Every batch below built to the same module set as its own baseline and was measured with
the same Arcan 1.2.1 jar. Batches that built a different module set are excluded entirely;
their counts are not comparable and are not reported here as results.

Smells are matched by identity, not by count. A cyclic dependency is identified by the SET
of packages (or classes) in it, an unstable dependency by the (package, correlated package)
pair, a hub-like by the class. So *removed* and *created* below are actual smells that
appeared or disappeared, and the net figure is what Arcan's total moved by.

## Counting correction applied to every number below

Arcan 1.2.1 writes both `UD.csv` and `UD30.csv`. `UD30` is the same unstable dependencies
filtered at a 30% instability threshold -- a severity view of `UD`, not a separate set of
findings. Every pair in it is already in `UD`: verified across all 63 Arcan runs in this
project, with no exceptions and no internally duplicated pairs. The adapter globbed
`UD*.csv` and read findings from both files, so every severe unstable dependency was
counted twice.

Totals here are therefore **distinct smells**, which lowers all three baselines:

| System | As previously counted | Distinct | Duplicated rows |
|---|---|---|---|
| Tika | 260 | **252** | 8 |
| log4j2 | 767 | **714** | 53 |
| Struts | 274 | **227** | 47 |

The inflation does not cancel in a delta, because the number of duplicated rows changes
with the tree: across these runs it ranges from 6 to 59. Three previously reported verdicts
change direction once restated, and log4j2-B1 -- the best arm B result -- falls from -16 to
-6. Both the old and the new figure are kept per batch in `results.json`
(`verdict_inflated` vs `verdict`) so the correction stays auditable.


---

## tika  (baseline 252 smells)

### tika-B3 — arm B, model suggestions

- moves applied: **4**
- Arcan total: **252 → 275 (net +23)**
- smells removed: **22**, smells created: **45**
- package cycles 68 → 91, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (4):

- `org.apache.tika.sax.TeeContentHandler`
- `org.apache.tika.detect.DefaultDetector`
- `org.apache.tika.metadata.OfficeOpenXMLExtended`
- `org.apache.tika.parser.AutoDetectParserConfig`

**Package cycles removed** (19):

- 2: `org.apache.tika.digest`, `org.apache.tika.parser`
- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.extractor`, `org.apache.tika.parser`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- … and 9 more

**Package cycles created** (42):

- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.metadata`, `org.apache.tika.metadata.writefilter`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.digest`, `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.metadata.writefilter`
- 4: `org.apache.tika.digest`, `org.apache.tika.extractor`, `org.apache.tika.metadata`, `org.apache.tika.metadata.writefilter`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.metadata.writefilter`, `org.apache.tika.sax`
- … and 32 more

**Class cycles removed** (1):

- 3: `org.apache.tika.Tika`, `org.apache.tika.detect.DefaultDetector`, `org.apache.tika.mime.MimeTypes`

**Class cycles created** (1):

- 3: `org.apache.tika.DefaultDetector`, `org.apache.tika.Tika`, `org.apache.tika.mime.MimeTypes`

**Unstable dependencies removed** (2): `org.apache.tika.parser` → `org.apache.tika.digest`; `org.apache.tika.serialization` → `org.apache.tika.metadata.writefilter`

**Unstable dependencies created** (2): `org.apache.tika.config.loader` → `org.apache.tika.metadata.writefilter`; `org.apache.tika.extractor` → `org.apache.tika`

### tika-B4 — arm B, model suggestions

- moves applied: **3**
- Arcan total: **252 → 261 (net +9)**
- smells removed: **18**, smells created: **27**
- package cycles 68 → 76, class cycles 105 → 105, unstable 78 → 79, hub-like 1 → 1

**Classes relocated** (3):

- `org.apache.tika.sax.ToXMLContentHandler`
- `org.apache.tika.sax.ToTextContentHandler`
- `org.apache.tika.sax.WriteOutContentHandler`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (26):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 16 more

**Unstable dependencies created** (1): `org.apache.tika.language.detect` → `org.apache.tika.parser`

### tika-B5 — arm B, model suggestions

- moves applied: **2**
- Arcan total: **252 → 253 (net +1)**
- smells removed: **0**, smells created: **1**
- package cycles 68 → 68, class cycles 105 → 105, unstable 78 → 79, hub-like 1 → 1

**Classes relocated** (2):

- `org.apache.tika.serialization.JsonMetadata`
- `org.apache.tika.sax.TextContentHandler`

**Unstable dependencies created** (1): `org.apache.tika.config.loader` → `org.apache.tika.serialization.serdes`

### tika-B6 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 258 (net +6)**
- smells removed: **19**, smells created: **25**
- package cycles 68 → 75, class cycles 105 → 105, unstable 78 → 77, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.sax.BasicContentHandlerFactory`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (25):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.mime`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 15 more

**Unstable dependencies removed** (1): `org.apache.tika.sax` → `org.apache.tika.config`

### tika-B7 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 252 (net +0)**
- smells removed: **10**, smells created: **10**
- package cycles 68 → 68, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.io.FilenameUtils`

**Package cycles removed** (1):

- 5: `org.apache.tika.io`, `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`

**Package cycles created** (1):

- 3: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`

**Class cycles removed** (8):

- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 8: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch` …
- 9: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (8):

- 4: `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.FilenameUtils`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.FilenameUtils`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.FilenameUtils`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.FilenameUtils` …
- 8: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …
- 9: `org.apache.tika.Tika`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser`, `org.apache.tika.parser.CompositeParser` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser` …

**Unstable dependencies removed** (1): `org.apache.tika.io` → `org.apache.tika.mime`

**Unstable dependencies created** (1): `org.apache.tika.io` → `org.apache.tika.parser`

### tika-B8 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 252 (net +0)**
- smells removed: **0**, smells created: **0**
- package cycles 68 → 68, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.extractor.EmbeddedDocumentExtractor`

### tika-B9 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 259 (net +7)**
- smells removed: **20**, smells created: **27**
- package cycles 68 → 75, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.sax.BodyContentHandler`

**Package cycles removed** (19):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.sax`, `org.apache.tika.sax.xpath`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- … and 9 more

**Package cycles created** (26):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 16 more

**Unstable dependencies removed** (1): `org.apache.tika.sax` → `org.apache.tika.sax.xpath`

**Unstable dependencies created** (1): `org.apache.tika.parser` → `org.apache.tika.sax.xpath`

### tika-B11 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 259 (net +7)**
- smells removed: **20**, smells created: **27**
- package cycles 68 → 75, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.sax.XHTMLContentHandler`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (25):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 15 more

**Unstable dependencies removed** (2): `org.apache.tika.sax` → `org.apache.tika.config`; `org.apache.tika.sax` → `org.apache.tika.parser`

**Unstable dependencies created** (2): `org.apache.tika.language.detect` → `org.apache.tika.sax`; `org.apache.tika.parser` → `org.apache.tika.sax`

### tika-B12 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 259 (net +7)**
- smells removed: **19**, smells created: **26**
- package cycles 68 → 76, class cycles 105 → 105, unstable 78 → 77, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.metadata.TikaCoreProperties`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (26):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 16 more

**Unstable dependencies removed** (1): `org.apache.tika.serialization` → `org.apache.tika.metadata.writefilter`

### tika-B13 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 258 (net +6)**
- smells removed: **28**, smells created: **34**
- package cycles 68 → 76, class cycles 105 → 105, unstable 78 → 76, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.parser.ParseContext`

**Package cycles removed** (22):

- 2: `org.apache.tika.digest`, `org.apache.tika.parser`
- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.metadata`, `org.apache.tika.metadata.writefilter`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser`, `org.apache.tika.renderer`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- … and 12 more

**Package cycles created** (30):

- 2: `org.apache.tika.metadata.writefilter`, `org.apache.tika.utils`
- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.config`, `org.apache.tika.metadata.writefilter`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika.metadata.writefilter`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.metadata.writefilter`, `org.apache.tika.utils`
- … and 20 more

**Unstable dependencies removed** (6): `org.apache.tika.mime` → `org.apache.tika.parser`; `org.apache.tika.parser` → `org.apache.tika.extractor`; `org.apache.tika.parser` → `org.apache.tika.utils`; `org.apache.tika.pipes.api` → `org.apache.tika.parser`; `org.apache.tika.pipes.api.fetcher` → `org.apache.tika.parser`; `org.apache.tika.serialization` → `org.apache.tika.metadata.writefilter`

**Unstable dependencies created** (4): `org.apache.tika.extractor` → `org.apache.tika.parser`; `org.apache.tika.metadata.writefilter` → `org.apache.tika.config`; `org.apache.tika.metadata.writefilter` → `org.apache.tika.utils`; `org.apache.tika.utils` → `org.apache.tika.parser`

### tika-B14 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **252 → 260 (net +8)**
- smells removed: **21**, smells created: **29**
- package cycles 68 → 75, class cycles 105 → 105, unstable 78 → 79, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.metadata.Metadata`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (25):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.mime`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 15 more

**Unstable dependencies removed** (3): `org.apache.tika.metadata` → `org.apache.tika.metadata.writefilter`; `org.apache.tika.metadata` → `org.apache.tika.utils`; `org.apache.tika.serialization` → `org.apache.tika.metadata.writefilter`

**Unstable dependencies created** (4): `org.apache.tika.metadata.writefilter` → `org.apache.tika.config`; `org.apache.tika.metadata.writefilter` → `org.apache.tika.metadata`; `org.apache.tika.metadata.writefilter` → `org.apache.tika.utils`; `org.apache.tika.sax` → `org.apache.tika.metadata`

### tika-C1 — arm C, DSARP planner

- moves applied: **10**
- Arcan total: **252 → 254 (net +2)**
- smells removed: **42**, smells created: **44**
- package cycles 68 → 78, class cycles 105 → 100, unstable 78 → 75, hub-like 1 → 1

**Classes relocated** (10):

- `org.apache.tika.eval.app.TikaEvalCLI`
- `org.apache.tika.eval.core.textstats.TokenCountPriorityQueue`
- `org.apache.tika.eval.core.tokens.TokenCounter`
- `org.apache.tika.parser.geo.topic.GeoParserConfig`
- `org.apache.tika.parser.geo.topic.gazetteer.GeoGazetteerClient`
- `org.apache.tika.parser.ner.NERecogniser`
- `org.apache.tika.parser.ner.NERecogniser`
- `org.apache.tika.parser.ner.NamedEntityParser`
- `org.apache.tika.parser.ner.NamedEntityParser`
- `org.apache.tika.parser.ner.regex.RegexNERecogniser`

**Package cycles removed** (32):

- 2: `org.apache.tika.parser.microsoft.onenote`, `org.apache.tika.parser.microsoft.onenote.fsshttpb`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`
- 2: `org.apache.tika.parser.geo.topic`, `org.apache.tika.parser.geo.topic.gazetteer`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.chunking`
- 2: `org.apache.tika.eval.core.textstats`, `org.apache.tika.eval.core.tokens`
- 2: `org.apache.tika.parser.ner`, `org.apache.tika.parser.ner.regex`
- 3: `org.apache.tika.parser.microsoft.onenote`, `org.apache.tika.parser.microsoft.onenote.fsshttpb`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- … and 22 more

**Package cycles created** (42):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.io`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 3: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika.parser.microsoft.onenote.fsshttpb`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.property`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`
- 3: `org.apache.tika.config`, `org.apache.tika.extractor`, `org.apache.tika.parser`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 32 more

**Class cycles removed** (6):

- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (1):

- 7: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …

**Unstable dependencies removed** (4): `org.apache.tika.eval.core.tokens` → `org.apache.tika.eval.core.textstats`; `org.apache.tika.parser.geo.topic.gazetteer` → `org.apache.tika.parser.geo.topic`; `org.apache.tika.parser.ner` → `org.apache.tika.parser.ner.opennlp`; `org.apache.tika.parser.ner` → `org.apache.tika.parser.ner.regex`

**Unstable dependencies created** (1): `org.apache.tika.parser.ner.opennlp` → `org.apache.tika.parser.ner`

### tika-C3 — arm C, DSARP planner

- moves applied: **12**
- Arcan total: **252 → 240 (net -12)**
- smells removed: **42**, smells created: **30**
- package cycles 68 → 64, class cycles 105 → 105, unstable 78 → 70, hub-like 1 → 1

**Classes relocated** (12):

- `org.apache.tika.parser.microsoft.onenote.fsshttpb.IFSSHTTPBSerializable`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.IFSSHTTPBSerializable`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PrtArrayOfPropertyValues`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PrtArrayOfPropertyValues`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic.CompactID`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic.HeaderCell`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic.PropertyID`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space.ObjectSpaceObjectPropSet`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.util.DataElementUtils`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.util.DataElementUtils`
- `org.apache.tika.parser.microsoft.ooxml.xslf.XSLFEventBasedPowerPointExtractor`
- `org.apache.tika.detect.microsoft.ooxml.OPCPackageDetector`

**Package cycles removed** (32):

- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`
- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser.microsoft.ooxml`, `org.apache.tika.parser.microsoft.ooxml.xslf`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.detect.microsoft.ooxml`, `org.apache.tika.parser.microsoft.ooxml`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 22 more

**Package cycles created** (28):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 18 more

**Class cycles removed** (1):

- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PrtArrayOfPropertyValues`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PropertySet`

**Class cycles created** (1):

- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PropertySet`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PrtArrayOfPropertyValues`

**Unstable dependencies removed** (9): `org.apache.tika.parser.microsoft.onenote.fsshttpb` → `org.apache.tika.parser.microsoft.onenote`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.property` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj` → `org.apache.tika.parser.microsoft.onenote.fsshttpb`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic` → `org.apache.tika.parser.microsoft.onenote.fsshttpb`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.util` …

**Unstable dependencies created** (1): `org.apache.tika.parser.microsoft.onenote` → `org.apache.tika.parser.microsoft.onenote.fsshttpb`

### tika-C4 — arm C, DSARP planner

- moves applied: **3**
- Arcan total: **252 → 250 (net -2)**
- smells removed: **41**, smells created: **39**
- package cycles 68 → 73, class cycles 105 → 100, unstable 78 → 76, hub-like 1 → 1

**Classes relocated** (3):

- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PropertySet`
- `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PropertySet`
- `org.apache.tika.detect.FileCommandDetector`

**Package cycles removed** (31):

- 2: `org.apache.tika.parser.microsoft.onenote`, `org.apache.tika.parser.microsoft.onenote.fsshttpb`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.chunking`
- 3: `org.apache.tika.parser.microsoft.onenote`, `org.apache.tika.parser.microsoft.onenote.fsshttpb`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.basic`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 21 more

**Package cycles created** (36):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.io`, `org.apache.tika.utils`
- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 3: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.config`, `org.apache.tika.extractor`, `org.apache.tika.parser`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.util`
- 3: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.renderer`
- … and 26 more

**Class cycles removed** (7):

- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PrtArrayOfPropertyValues`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.PropertySet`
- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (2):

- 2: `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PropertySet`, `org.apache.tika.parser.microsoft.onenote.fsshttpb.property.PrtArrayOfPropertyValues`
- 7: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …

**Unstable dependencies removed** (3): `org.apache.tika.detect` → `org.apache.tika.parser.external`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.property` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`; `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj`

**Unstable dependencies created** (1): `org.apache.tika.parser.microsoft.onenote.fsshttpb.streamobj.space` → `org.apache.tika.parser.microsoft.onenote.fsshttpb.property`

### tika-C5 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **252 → 259 (net +7)**
- smells removed: **20**, smells created: **27**
- package cycles 68 → 75, class cycles 105 → 105, unstable 78 → 78, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.serialization.serdes.ParseContextDeserializer`

**Package cycles removed** (19):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.config.loader`, `org.apache.tika.serialization`, `org.apache.tika.serialization.serdes`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- … and 9 more

**Package cycles created** (26):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 16 more

**Unstable dependencies removed** (1): `org.apache.tika.serialization.serdes` → `org.apache.tika.serialization`

**Unstable dependencies created** (1): `org.apache.tika.serialization` → `org.apache.tika.serialization.serdes`

### tika-C6 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **252 → 253 (net +1)**
- smells removed: **27**, smells created: **28**
- package cycles 68 → 75, class cycles 105 → 100, unstable 78 → 77, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.detect.microsoft.POIFSContainerDetector`

**Package cycles removed** (19):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 2: `org.apache.tika.detect.microsoft`, `org.apache.tika.parser.microsoft`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- … and 9 more

**Package cycles created** (26):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.detect`, `org.apache.tika.mime`, `org.apache.tika.parser.external`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 16 more

**Class cycles removed** (7):

- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.microsoft.POIFSContainerDetector`, `org.apache.tika.parser.microsoft.AbstractPOIFSExtractor`, `org.apache.tika.parser.microsoft.OfficeParser`, `org.apache.tika.parser.microsoft.OfficeParser$POIFSDocumentType`, `org.apache.tika.parser.microsoft.SummaryExtractor`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (2):

- 5: `org.apache.tika.parser.microsoft.AbstractPOIFSExtractor`, `org.apache.tika.parser.microsoft.OfficeParser`, `org.apache.tika.parser.microsoft.OfficeParser$POIFSDocumentType`, `org.apache.tika.parser.microsoft.POIFSContainerDetector`, `org.apache.tika.parser.microsoft.SummaryExtractor`
- 7: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …

**Unstable dependencies removed** (1): `org.apache.tika.parser.microsoft` → `org.apache.tika.detect.microsoft`

### tika-C7 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **252 → 249 (net -3)**
- smells removed: **25**, smells created: **22**
- package cycles 68 → 71, class cycles 105 → 100, unstable 78 → 77, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.parser.external.ExternalParser`

**Package cycles removed** (18):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 8 more

**Package cycles created** (21):

- 2: `org.apache.tika.io`, `org.apache.tika.mime`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.mime`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 11 more

**Class cycles removed** (6):

- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (1):

- 7: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …

**Unstable dependencies removed** (1): `org.apache.tika.detect` → `org.apache.tika.parser.external`

### tika-C8 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **252 → 250 (net -2)**
- smells removed: **2**, smells created: **0**
- package cycles 68 → 67, class cycles 105 → 105, unstable 78 → 77, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.server.core.MetadataList`

**Package cycles removed** (1):

- 2: `org.apache.tika.server.core`, `org.apache.tika.server.core.writer`

**Unstable dependencies removed** (1): `org.apache.tika.server.core` → `org.apache.tika.server.core.writer`

### tika-C9 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **252 → 253 (net +1)**
- smells removed: **30**, smells created: **31**
- package cycles 68 → 73, class cycles 105 → 99, unstable 78 → 80, hub-like 1 → 1

**Classes relocated** (1):

- `org.apache.tika.Tika`

**Package cycles removed** (19):

- 2: `org.apache.tika.parser`, `org.apache.tika.sax`
- 2: `org.apache.tika`, `org.apache.tika.mime`
- 2: `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika`, `org.apache.tika.detect`, `org.apache.tika.mime`
- 3: `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.mime`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.extractor`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.parser.multiple`, `org.apache.tika.utils`
- 3: `org.apache.tika.digest`, `org.apache.tika.parser`, `org.apache.tika.utils`
- 3: `org.apache.tika.parser`, `org.apache.tika.renderer`, `org.apache.tika.utils`
- … and 9 more

**Package cycles created** (24):

- 2: `org.apache.tika.io`, `org.apache.tika.sax`
- 2: `org.apache.tika.sax`, `org.apache.tika.utils`
- 2: `org.apache.tika.config`, `org.apache.tika.utils`
- 2: `org.apache.tika.detect`, `org.apache.tika.io`
- 3: `org.apache.tika.config`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.mime`
- 3: `org.apache.tika.io`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 3: `org.apache.tika.detect`, `org.apache.tika.io`, `org.apache.tika.parser.external`
- 4: `org.apache.tika.config`, `org.apache.tika.parser`, `org.apache.tika.sax`, `org.apache.tika.utils`
- 4: `org.apache.tika.io`, `org.apache.tika.metadata`, `org.apache.tika.sax`, `org.apache.tika.utils`
- … and 14 more

**Class cycles removed** (9):

- 3: `org.apache.tika.Tika`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser`
- 3: `org.apache.tika.Tika`, `org.apache.tika.detect.DefaultDetector`, `org.apache.tika.mime.MimeTypes`
- 4: `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 5: `org.apache.tika.detect.TextDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes`
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 7: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …
- 9: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser` …
- 11: `org.apache.tika.Tika`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TemporaryResources`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MimeTypes` …

**Class cycles created** (3):

- 3: `org.apache.tika.detect.DefaultDetector`, `org.apache.tika.io.Tika`, `org.apache.tika.mime.MimeTypes`
- 3: `org.apache.tika.io.Tika`, `org.apache.tika.mime.MimeTypes`, `org.apache.tika.parser.AutoDetectParser`
- 7: `org.apache.tika.detect.MagicDetector`, `org.apache.tika.io.FilenameUtils`, `org.apache.tika.io.TikaInputStream`, `org.apache.tika.mime.MagicMatch`, `org.apache.tika.mime.MimeTypes` …

**Unstable dependencies removed** (2): `org.apache.tika` → `org.apache.tika.detect`; `org.apache.tika.mime` → `org.apache.tika`

**Unstable dependencies created** (4): `org.apache.tika.io` → `org.apache.tika.detect`; `org.apache.tika.io` → `org.apache.tika.language.translate`; `org.apache.tika.io` → `org.apache.tika.parser`; `org.apache.tika.sax` → `org.apache.tika.io`


---

## log4j2  (baseline 714 smells)

### log4j2-B1 — arm B, model suggestions

- moves applied: **25**
- Arcan total: **714 → 708 (net -6)**
- smells removed: **60**, smells created: **54**
- package cycles 201 → 199, class cycles 380 → 377, unstable 130 → 129, hub-like 3 → 3

**Classes relocated** (25):

- `org.apache.log4j.CustomFileAppender`
- `org.apache.log4j.CustomNoopAppender`
- `org.apache.log4j.bridge.AppenderAdapter`
- `org.apache.log4j.bridge.AppenderWrapper`
- `org.apache.log4j.bridge.FilterAdapter`
- `org.apache.log4j.builders.BuilderManager`
- `org.apache.log4j.builders.rewrite.RewritePolicyBuilder`
- `org.apache.log4j.builders.rolling.TriggeringPolicyBuilder`
- `org.apache.log4j.config.Log4j1Configuration`
- `org.apache.log4j.helpers.AppenderAttachableImpl`
- `org.apache.log4j.helpers.LogLog`
- `org.apache.log4j.or.ObjectRenderer`
- `org.apache.log4j.spi.LoggerRepository`
- `org.apache.log4j.spi.RendererSupport`
- … and 11 more

**Package cycles removed** (16):

- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.filter`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.rolling`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.layout`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.rewrite`
- 3: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`
- 3: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.xml`
- 4: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.builders.filter`, `org.apache.log4j.config`
- 4: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`
- 4: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.xml`
- … and 6 more

**Package cycles created** (14):

- 2: `org.apache.log4j`, `org.apache.log4j.legacy.core`
- 2: `org.apache.log4j.builders.appender`, `org.apache.log4j.config`
- 3: `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.xml`
- 3: `org.apache.log4j`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`
- 3: `org.apache.log4j`, `org.apache.log4j.builders.filter`, `org.apache.log4j.config`
- 3: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.config`
- 4: `org.apache.log4j`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.xml`
- 5: `org.apache.log4j`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.spi`, `org.apache.log4j.xml`
- 5: `org.apache.log4j`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 5: `org.apache.log4j`, `org.apache.log4j.builders.filter`, `org.apache.log4j.config`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- … and 4 more

**Class cycles removed** (36):

- 2: `org.apache.logging.log4j.core.appender.rolling.action.PosixViewAttributeAction`, `org.apache.logging.log4j.core.appender.rolling.action.PosixViewAttributeAction$1`
- 2: `org.apache.logging.log4j.core.appender.rolling.action.PosixViewAttributeAction`, `org.apache.logging.log4j.core.appender.rolling.action.PosixViewAttributeAction$Builder`
- 2: `org.apache.log4j.bridge.FilterAdapter`, `org.apache.log4j.bridge.FilterWrapper`
- 2: `org.apache.log4j.helpers.LogLog`, `org.apache.log4j.helpers.OptionConverter`
- 2: `org.apache.log4j.Category`, `org.apache.log4j.Hierarchy`
- 3: `org.apache.log4j.Category`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`
- 3: `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderAdapter$Adapter`, `org.apache.log4j.bridge.AppenderWrapper`
- 5: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderAdapter$Adapter`, `org.apache.log4j.bridge.AppenderWrapper`, `org.apache.log4j.bridge.LogEventAdapter`
- 6: `org.apache.log4j.PropertyConfigurator`, `org.apache.log4j.builders.AbstractBuilder`, `org.apache.log4j.builders.BuilderManager`, `org.apache.log4j.config.Log4j1Configuration`, `org.apache.log4j.config.PropertiesConfiguration` …
- 6: `org.apache.log4j.DefaultCategoryFactory`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.Logger`, `org.apache.log4j.PropertyConfigurator` …
- … and 26 more

**Class cycles created** (33):

- 2: `org.apache.log4j.FilterAdapter`, `org.apache.log4j.bridge.FilterWrapper`
- 2: `org.apache.logging.log4j.core.appender.rolling.PosixViewAttributeAction`, `org.apache.logging.log4j.core.appender.rolling.PosixViewAttributeAction$Builder`
- 2: `org.apache.logging.log4j.core.appender.rolling.PosixViewAttributeAction`, `org.apache.logging.log4j.core.appender.rolling.PosixViewAttributeAction$1`
- 2: `org.apache.log4j.helpers.OptionConverter`, `org.apache.log4j.spi.LogLog`
- 3: `org.apache.log4j.PropertyConfigurator`, `org.apache.log4j.helpers.OptionConverter`, `org.apache.log4j.or.RendererMap`
- 3: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 3: `org.apache.log4j.AppenderAdapter`, `org.apache.log4j.AppenderAdapter$Adapter`, `org.apache.log4j.AppenderWrapper`
- 4: `org.apache.log4j.AppenderAdapter`, `org.apache.log4j.AppenderWrapper`, `org.apache.log4j.Category`, `org.apache.log4j.bridge.LogEventAdapter`
- 4: `org.apache.logging.log4j.core.tools.Generate`, `org.apache.logging.log4j.core.tools.Generate$ExtendedLogger`, `org.apache.logging.log4j.core.tools.Generate$Type`, `org.apache.logging.log4j.core.tools.Generate$Type$2`
- 4: `org.apache.log4j.AppenderAdapter`, `org.apache.log4j.Category`, `org.apache.log4j.FilterAdapter`, `org.apache.log4j.bridge.LogEventAdapter`
- … and 23 more

**Unstable dependencies removed** (8): `org.apache.log4j.bridge` → `org.apache.logging.log4j.core.appender`; `org.apache.log4j.bridge` → `org.apache.logging.log4j.core.filter`; `org.apache.log4j.builders` → `org.apache.log4j.builders.appender`; `org.apache.log4j.builders` → `org.apache.log4j.builders.filter`; `org.apache.log4j.builders` → `org.apache.log4j.builders.layout`; `org.apache.log4j.builders` → `org.apache.log4j.builders.rewrite` …

**Unstable dependencies created** (7): `org.apache.log4j` → `org.apache.logging.log4j.core.filter`; `org.apache.log4j.builders` → `org.apache.log4j`; `org.apache.log4j.builders` → `org.apache.log4j.bridge`; `org.apache.log4j.config` → `org.apache.log4j.builders.appender`; `org.apache.log4j.config` → `org.apache.log4j.builders.filter`; `org.apache.log4j.config` → `org.apache.log4j.builders.layout` …

### log4j2-B2 — arm B, model suggestions

- moves applied: **25**
- Arcan total: **714 → 735 (net +21)**
- smells removed: **98**, smells created: **119**
- package cycles 201 → 207, class cycles 380 → 389, unstable 130 → 136, hub-like 3 → 3

**Classes relocated** (25):

- `org.apache.logging.log4j.core.config.plugins.visitors.PluginAttributeVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginBuilderAttributeVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginConfigurationVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginElementVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginLoggerContextVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginNodeVisitor`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginValueVisitor`
- `org.apache.logging.log4j.core.test.ExtendedLevels`
- `org.apache.logging.log4j.core.test.appender.BlockingAppender`
- `org.apache.logging.log4j.core.test.appender.FailOnceAppender`
- `org.apache.logging.log4j.core.test.appender.InMemoryAppender`
- `org.apache.logging.log4j.core.test.junit.JdbcRule`
- `org.apache.logging.log4j.core.util.internal.HttpInputStreamUtil`
- `org.apache.logging.log4j.core.util.internal.LastModifiedSource`
- … and 11 more

**Package cycles removed** (82):

- 2: `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 2: `org.apache.logging.log4j.simple.internal`, `org.apache.logging.log4j.util`
- 2: `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.or`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.spi`
- 3: `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`, `org.apache.logging.log4j.core.lookup`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.net`, `org.apache.logging.log4j.core.selector`
- 4: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.builders`, `org.apache.log4j.config`
- 4: `org.apache.log4j`, `org.apache.log4j.helpers`, `org.apache.log4j.or`, `org.apache.log4j.spi`
- 4: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- … and 72 more

**Package cycles created** (88):

- 2: `org.apache.log4j`, `org.apache.log4j.helpers`
- 2: `org.apache.logging.log4j.core.config.plugins`, `org.apache.logging.log4j.core.config.plugins.util`
- 2: `org.apache.log4j.bridge`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.helpers`, `org.apache.log4j.or`
- 3: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.spi`
- 3: `org.apache.logging.log4j.core.config.plugins`, `org.apache.logging.log4j.core.config.plugins.processor`, `org.apache.logging.log4j.core.config.plugins.util`
- 3: `org.apache.logging.log4j.core.config.plugins`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 3: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.helpers`
- 3: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins`
- 3: `org.apache.log4j.bridge`, `org.apache.log4j.rewrite`, `org.apache.log4j.spi`
- … and 78 more

**Class cycles removed** (10):

- 2: `org.apache.logging.log4j.core.config.arbiters.SelectArbiter`, `org.apache.logging.log4j.core.config.arbiters.SelectArbiter$Builder`
- 2: `org.apache.logging.log4j.core.test.junit.JdbcRule`, `org.apache.logging.log4j.core.test.junit.JdbcRule$1`
- 2: `org.apache.log4j.Category`, `org.apache.log4j.Hierarchy`
- 2: `org.apache.logging.log4j.test.junit.SecurityManagerTestRule`, `org.apache.logging.log4j.test.junit.SecurityManagerTestRule$1`
- 3: `org.apache.log4j.Category`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`
- 4: `org.apache.logging.log4j.internal.DefaultLogBuilder`, `org.apache.logging.log4j.spi.AbstractLogger`, `org.apache.logging.log4j.status.StatusLogger`, `org.apache.logging.log4j.util.StackLocatorUtil`
- 6: `org.apache.log4j.DefaultCategoryFactory`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.Logger`, `org.apache.log4j.PropertyConfigurator` …
- 7: `org.apache.log4j.Category`, `org.apache.log4j.DefaultCategoryFactory`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.Logger` …
- 8: `org.apache.log4j.Category`, `org.apache.log4j.DefaultCategoryFactory`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.Logger` …
- 11: `org.apache.log4j.Category`, `org.apache.log4j.DefaultCategoryFactory`, `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.Logger` …

**Class cycles created** (19):

- 2: `org.apache.logging.log4j.core.appender.db.jdbc.JdbcRule`, `org.apache.logging.log4j.core.appender.db.jdbc.JdbcRule$1`
- 2: `org.apache.logging.log4j.util.SecurityManagerTestRule`, `org.apache.logging.log4j.util.SecurityManagerTestRule$1`
- 2: `org.apache.logging.log4j.core.config.SelectArbiter`, `org.apache.logging.log4j.core.config.SelectArbiter$Builder`
- 3: `org.apache.log4j.PropertyConfigurator`, `org.apache.log4j.helpers.OptionConverter`, `org.apache.log4j.or.RendererMap`
- 4: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.FilterAdapter`, `org.apache.log4j.bridge.LogEventAdapter`
- 4: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderWrapper`, `org.apache.log4j.bridge.LogEventAdapter`
- 5: `org.apache.log4j.Hierarchy`, `org.apache.log4j.LogManager`, `org.apache.log4j.PropertyConfigurator`, `org.apache.log4j.helpers.OptionConverter`, `org.apache.log4j.or.RendererMap`
- 5: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderWrapper`, `org.apache.log4j.bridge.LayoutWrapper`, `org.apache.log4j.bridge.LogEventAdapter`
- 5: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderWrapper`, `org.apache.log4j.bridge.ErrorHandlerAdapter`, `org.apache.log4j.bridge.LogEventAdapter`
- 5: `org.apache.log4j.Category`, `org.apache.log4j.bridge.AppenderAdapter`, `org.apache.log4j.bridge.AppenderWrapper`, `org.apache.log4j.bridge.FilterAdapter`, `org.apache.log4j.bridge.LogEventAdapter`
- … and 9 more

**Unstable dependencies removed** (6): `org.apache.logging.log4j` → `org.apache.logging.log4j.internal`; `org.apache.logging.log4j.core.config` → `org.apache.logging.log4j.core.util.internal`; `org.apache.logging.log4j.core.config.plugins.util` → `org.apache.logging.log4j.core.config.plugins.visitors`; `org.apache.logging.log4j.core.util` → `org.apache.logging.log4j.core.time`; `org.apache.logging.log4j.core.util.internal` → `org.apache.logging.log4j.core.net.ssl`; `org.apache.logging.log4j.util` → `org.apache.logging.log4j.simple.internal`

**Unstable dependencies created** (12): `org.apache.logging.log4j.core.config` → `org.apache.logging.log4j.core.net.ssl`; `org.apache.logging.log4j.core.config.plugins` → `org.apache.logging.log4j`; `org.apache.logging.log4j.core.config.plugins` → `org.apache.logging.log4j.core`; `org.apache.logging.log4j.core.config.plugins` → `org.apache.logging.log4j.core.config`; `org.apache.logging.log4j.core.config.plugins` → `org.apache.logging.log4j.core.config.plugins.util`; `org.apache.logging.log4j.core.config.plugins` → `org.apache.logging.log4j.core.config.plugins.visitors` …

### log4j2-B3 — arm B, model suggestions

- moves applied: **25**
- Arcan total: **714 → 730 (net +16)**
- smells removed: **194**, smells created: **210**
- package cycles 201 → 198, class cycles 380 → 398, unstable 130 → 131, hub-like 3 → 3

**Classes relocated** (25):

- `org.apache.logging.log4j.core.config.plugins.validation.validators.RequiredValidator`
- `org.apache.logging.log4j.core.config.plugins.validation.validators.ValidHostValidator`
- `org.apache.logging.log4j.core.config.plugins.validation.validators.ValidPortValidator`
- `org.apache.logging.log4j.core.config.plugins.visitors.PluginVisitor`
- `org.apache.logging.log4j.core.impl.ThreadContextDataInjector`
- `org.apache.logging.log4j.core.impl.ThrowableFormatOptions`
- `org.apache.logging.log4j.core.jmx.RingBufferAdmin`
- `org.apache.logging.log4j.core.layout.LoggerFields`
- `org.apache.logging.log4j.core.net.Advertiser`
- `org.apache.logging.log4j.core.script.AbstractScript`
- `org.apache.logging.log4j.core.script.ScriptManager`
- `org.apache.logging.log4j.core.script.ScriptRef`
- `org.apache.logging.log4j.core.test.GcFreeLoggingTestUtil`
- `org.apache.logging.log4j.core.test.appender.db.jdbc.JdbcH2TestHelper`
- … and 11 more

**Package cycles removed** (140):

- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.composite`
- 2: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.selector`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`
- 2: `org.apache.log4j.builders`, `org.apache.log4j.builders.filter`
- 2: `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.pattern`
- 2: `org.apache.logging.log4j.core.layout`, `org.apache.logging.log4j.core.net`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.impl`
- 3: `org.apache.logging.log4j`, `org.apache.logging.log4j.message`, `org.apache.logging.log4j.spi`
- 3: `org.apache.logging.log4j.message`, `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.status`
- 3: `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`
- … and 130 more

**Package cycles created** (137):

- 2: `org.apache.logging.log4j.message`, `org.apache.logging.log4j.test`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.script`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.layout`
- 2: `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.test`
- 2: `org.apache.logging.log4j.core.layout`, `org.apache.logging.log4j.core.pattern`
- 3: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.jmx`, `org.apache.logging.log4j.core.selector`
- 3: `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.validation.constraints`
- 3: `org.apache.logging.log4j.core.config.composite`, `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.lookup`
- 3: `org.apache.logging.log4j.core.config.composite`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl`
- 3: `org.apache.logging.log4j`, `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.test`
- … and 127 more

**Class cycles removed** (48):

- 2: `org.apache.logging.log4j.core.layout.PatternLayout`, `org.apache.logging.log4j.core.layout.PatternLayout$Builder`
- 2: `org.apache.logging.log4j.core.test.appender.db.jdbc.JdbcH2TestHelper`, `org.apache.logging.log4j.core.test.appender.db.jdbc.JdbcH2TestHelper$2`
- 2: `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner$1`
- 2: `org.apache.logging.log4j.core.test.GcFreeLoggingTestUtil`, `org.apache.logging.log4j.core.test.GcFreeLoggingTestUtil$MyCharSeq`
- 2: `org.apache.logging.log4j.core.test.appender.db.jdbc.JdbcH2TestHelper`, `org.apache.logging.log4j.core.test.appender.db.jdbc.JdbcH2TestHelper$1`
- 2: `org.apache.logging.log4j.core.jmx.RingBufferAdmin`, `org.apache.logging.log4j.core.jmx.Server`
- 2: `org.apache.logging.log4j.core.test.junit.JndiRule`, `org.apache.logging.log4j.core.test.junit.JndiRule$1`
- 3: `org.apache.logging.log4j.core.script.ScriptManager`, `org.apache.logging.log4j.core.script.ScriptManager$AbstractScriptRunner`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner`
- 3: `org.apache.logging.log4j.core.script.ScriptManager`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner$1`
- 4: `org.apache.logging.log4j.core.script.ScriptManager`, `org.apache.logging.log4j.core.script.ScriptManager$MainScriptRunner`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner`, `org.apache.logging.log4j.core.script.ScriptManager$ThreadLocalScriptRunner$1`
- … and 38 more

**Class cycles created** (66):

- 2: `org.apache.logging.log4j.core.async.RingBufferAdmin`, `org.apache.logging.log4j.core.jmx.Server`
- 2: `org.apache.logging.log4j.core.appender.db.jdbc.JdbcH2TestHelper`, `org.apache.logging.log4j.core.appender.db.jdbc.JdbcH2TestHelper$1`
- 2: `org.apache.logging.log4j.core.GcFreeLoggingTestUtil`, `org.apache.logging.log4j.core.GcFreeLoggingTestUtil$MyCharSeq`
- 2: `org.apache.logging.log4j.core.config.ScriptManager$ThreadLocalScriptRunner`, `org.apache.logging.log4j.core.config.ScriptManager$ThreadLocalScriptRunner$1`
- 2: `org.apache.logging.log4j.core.lookup.JndiRule`, `org.apache.logging.log4j.core.lookup.JndiRule$1`
- 2: `org.apache.logging.log4j.core.appender.db.jdbc.JdbcH2TestHelper`, `org.apache.logging.log4j.core.appender.db.jdbc.JdbcH2TestHelper$2`
- 3: `org.apache.logging.log4j.core.config.ScriptManager`, `org.apache.logging.log4j.core.config.ScriptManager$AbstractScriptRunner`, `org.apache.logging.log4j.core.config.ScriptManager$ThreadLocalScriptRunner`
- 3: `org.apache.logging.log4j.core.config.ScriptManager`, `org.apache.logging.log4j.core.config.ScriptManager$ThreadLocalScriptRunner`, `org.apache.logging.log4j.core.config.ScriptManager$ThreadLocalScriptRunner$1`
- 3: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 3: `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`, `org.apache.logging.log4j.core.lookup.StrSubstitutor`
- … and 56 more

**Unstable dependencies removed** (6): `org.apache.log4j.builders` → `org.apache.log4j.builders.appender`; `org.apache.log4j.builders` → `org.apache.log4j.builders.filter`; `org.apache.logging.log4j.core` → `org.apache.logging.log4j.util`; `org.apache.logging.log4j.core.appender` → `org.apache.logging.log4j.core.script`; `org.apache.logging.log4j.core.layout` → `org.apache.logging.log4j.core.script`; `org.apache.logging.log4j.core.util` → `org.apache.logging.log4j.core.time`

**Unstable dependencies created** (7): `org.apache.logging.log4j.core.config.plugins.validation.constraints` → `org.apache.logging.log4j.core.config.plugins.convert`; `org.apache.logging.log4j.core.config.plugins.validation.constraints` → `org.apache.logging.log4j.core.util`; `org.apache.logging.log4j.core.time` → `org.apache.logging.log4j.core.util`; `org.apache.logging.log4j.core.util` → `org.apache.logging.log4j.spi`; `org.apache.logging.log4j.layout.template.json` → `org.apache.logging.log4j.core.config.plugins.convert`; `org.apache.logging.log4j.message` → `org.apache.logging.log4j.test` …

### log4j2-B7 — arm B, model suggestions

- moves applied: **2**
- Arcan total: **714 → 713 (net -1)**
- smells removed: **1**, smells created: **0**
- package cycles 201 → 201, class cycles 380 → 379, unstable 130 → 130, hub-like 3 → 3

**Classes relocated** (2):

- `org.apache.log4j.ListAppender`
- `org.apache.logging.log4j.message.MessageFactory`

**Class cycles removed** (1):

- 4: `org.apache.logging.log4j.internal.DefaultLogBuilder`, `org.apache.logging.log4j.spi.AbstractLogger`, `org.apache.logging.log4j.status.StatusLogger`, `org.apache.logging.log4j.util.StackLocatorUtil`

### log4j2-B11 — arm B, model suggestions

- moves applied: **1**
- Arcan total: **714 → 729 (net +15)**
- smells removed: **157**, smells created: **172**
- package cycles 201 → 199, class cycles 380 → 398, unstable 130 → 129, hub-like 3 → 3

**Classes relocated** (1):

- `org.apache.logging.log4j.core.util.Source`

**Package cycles removed** (129):

- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.composite`
- 2: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.selector`
- 2: `org.apache.logging.log4j.message`, `org.apache.logging.log4j.status`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.impl`
- 3: `org.apache.logging.log4j`, `org.apache.logging.log4j.message`, `org.apache.logging.log4j.spi`
- 3: `org.apache.logging.log4j.message`, `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.status`
- 3: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.impl`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.net`, `org.apache.logging.log4j.core.selector`
- 4: `org.apache.logging.log4j`, `org.apache.logging.log4j.message`, `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.status`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.jmx`
- … and 119 more

**Package cycles created** (127):

- 2: `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.status`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.util`
- 2: `org.apache.logging.log4j.message`, `org.apache.logging.log4j.util`
- 3: `org.apache.logging.log4j`, `org.apache.logging.log4j.spi`, `org.apache.logging.log4j.status`
- 3: `org.apache.logging.log4j.core.config.composite`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl`
- 3: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.util`
- 3: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.properties`, `org.apache.logging.log4j.core.util`
- 3: `org.apache.logging.log4j`, `org.apache.logging.log4j.message`, `org.apache.logging.log4j.util`
- 3: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.arbiters`, `org.apache.logging.log4j.core.util`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.time`, `org.apache.logging.log4j.core.util`
- … and 117 more

**Class cycles removed** (27):

- 2: `org.apache.logging.log4j.core.layout.PatternLayout`, `org.apache.logging.log4j.core.layout.PatternLayout$Builder`
- 2: `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.util.Source`
- 6: `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.NullConfiguration`, `org.apache.logging.log4j.core.lookup.Interpolator` …
- 7: `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory`, `org.apache.logging.log4j.core.config.builder.impl.BuiltConfiguration` …
- 8: `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFileWatcher`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory` …
- 8: `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory`, `org.apache.logging.log4j.core.config.builder.impl.BuiltConfiguration` …
- 9: `org.apache.logging.log4j.core.appender.AbstractAppender$Builder`, `org.apache.logging.log4j.core.appender.AbstractOutputStreamAppender$Builder`, `org.apache.logging.log4j.core.appender.ConsoleAppender`, `org.apache.logging.log4j.core.appender.ConsoleAppender$Builder`, `org.apache.logging.log4j.core.config.AbstractConfiguration` …
- 9: `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory` …
- 9: `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFileWatcher`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory` …
- 10: `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationSource` …
- … and 17 more

**Class cycles created** (45):

- 2: `org.apache.logging.log4j.core.Source`, `org.apache.logging.log4j.core.config.ConfigurationSource`
- 3: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 3: `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`, `org.apache.logging.log4j.core.lookup.StrSubstitutor`
- 4: `org.apache.logging.log4j.core.config.PropertiesPlugin`, `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`, `org.apache.logging.log4j.core.lookup.StrSubstitutor`
- 4: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 5: `org.apache.logging.log4j.core.config.Configuration`, `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.ConfigurationStrSubstitutor`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`, `org.apache.logging.log4j.core.lookup.StrSubstitutor`
- 9: `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.Configuration`, `org.apache.logging.log4j.core.config.PropertiesPlugin`, `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.ConfigurationStrSubstitutor` …
- 10: `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.Configuration`, `org.apache.logging.log4j.core.config.PropertiesPlugin`, `org.apache.logging.log4j.core.config.Property` …
- 10: `org.apache.logging.log4j.core.Logger`, `org.apache.logging.log4j.core.Logger$PrivateConfig`, `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.LoggerConfig` …
- 10: `org.apache.logging.log4j.core.async.AsyncLoggerConfigDisruptor`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory` …
- … and 35 more

**Unstable dependencies removed** (1): `org.apache.logging.log4j.core` → `org.apache.logging.log4j.util`

### log4j2-C3 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **714 → 714 (net +0)**
- smells removed: **83**, smells created: **83**
- package cycles 201 → 201, class cycles 380 → 379, unstable 130 → 131, hub-like 3 → 3

**Classes relocated** (1):

- `org.apache.logging.log4j.core.config.plugins.util.PluginBuilder`

**Package cycles removed** (80):

- 2: `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 3: `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 3: `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`, `org.apache.logging.log4j.core.lookup`
- 5: `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors`, `org.apache.logging.log4j.core.lookup`
- 6: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.pattern`, `org.apache.logging.log4j.core.util`, `org.apache.logging.log4j.perf.nogc`, `org.apache.logging.log4j.spi` …
- 6: `org.apache.logging.log4j.core.appender.rolling`, `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.visitors` …
- 7: `org.apache.logging.log4j`, `org.apache.logging.log4j.core`, `org.apache.logging.log4j.core.time`, `org.apache.logging.log4j.core.util`, `org.apache.logging.log4j.perf.nogc` …
- 7: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.layout`, `org.apache.logging.log4j.core.lookup` …
- 7: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.pattern`, `org.apache.logging.log4j.core.time`, `org.apache.logging.log4j.core.util`, `org.apache.logging.log4j.perf.nogc` …
- 7: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.pattern`, `org.apache.logging.log4j.core.util`, `org.apache.logging.log4j.perf.nogc` …
- … and 70 more

**Package cycles created** (80):

- 2: `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.util`
- 2: `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 4: `org.apache.logging.log4j.core.config.plugins.processor`, `org.apache.logging.log4j.core.config.plugins.processor.internal`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.util`
- 4: `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 5: `org.apache.logging.log4j.core.appender.rolling`, `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.visitors`
- 6: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.pattern`, `org.apache.logging.log4j.perf.nogc`, `org.apache.logging.log4j.spi` …
- 6: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.layout`, `org.apache.logging.log4j.core.net`, `org.apache.logging.log4j.core.script` …
- 7: `org.apache.logging.log4j.core.appender.rolling`, `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.visitors` …
- 7: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.visitors`, `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.pattern` …
- 7: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.pattern`, `org.apache.logging.log4j.core.util`, `org.apache.logging.log4j.perf.nogc` …
- … and 70 more

**Class cycles removed** (2):

- 2: `org.apache.logging.log4j.core.config.plugins.util.PluginBuilder`, `org.apache.logging.log4j.core.util.Builder`
- 4: `org.apache.logging.log4j.internal.DefaultLogBuilder`, `org.apache.logging.log4j.spi.AbstractLogger`, `org.apache.logging.log4j.status.StatusLogger`, `org.apache.logging.log4j.util.StackLocatorUtil`

**Class cycles created** (1):

- 2: `org.apache.logging.log4j.core.config.plugins.visitors.PluginBuilder`, `org.apache.logging.log4j.core.util.Builder`

**Unstable dependencies removed** (1): `org.apache.logging.log4j.core.config.plugins.util` → `org.apache.logging.log4j.core.config.plugins.visitors`

**Unstable dependencies created** (2): `org.apache.logging.log4j.core.config` → `org.apache.logging.log4j.core.config.plugins.visitors`; `org.apache.logging.log4j.core.util` → `org.apache.logging.log4j.core.config.plugins.visitors`

### log4j2-C4 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **714 → 708 (net -6)**
- smells removed: **19**, smells created: **13**
- package cycles 201 → 197, class cycles 380 → 379, unstable 130 → 129, hub-like 3 → 3

**Classes relocated** (1):

- `org.apache.log4j.spi.RootLogger`

**Package cycles removed** (16):

- 2: `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.or`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 4: `org.apache.log4j`, `org.apache.log4j.helpers`, `org.apache.log4j.or`, `org.apache.log4j.spi`
- 4: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.builders`, `org.apache.log4j.config`
- 4: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 5: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.builders`, `org.apache.log4j.config`, `org.apache.log4j.spi`
- 5: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.config`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 6: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.builders`, `org.apache.log4j.config`, `org.apache.log4j.helpers` …
- … and 6 more

**Package cycles created** (12):

- 2: `org.apache.log4j`, `org.apache.log4j.helpers`
- 2: `org.apache.log4j.bridge`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.helpers`, `org.apache.log4j.or`
- 3: `org.apache.log4j.bridge`, `org.apache.log4j.rewrite`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.spi`
- 3: `org.apache.log4j`, `org.apache.log4j.config`, `org.apache.log4j.helpers`
- 4: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.config`, `org.apache.log4j.helpers`
- 4: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.helpers`, `org.apache.log4j.spi`
- 5: `org.apache.log4j`, `org.apache.log4j.bridge`, `org.apache.log4j.helpers`, `org.apache.log4j.rewrite`, `org.apache.log4j.spi`
- 5: `org.apache.log4j`, `org.apache.log4j.builders`, `org.apache.log4j.builders.appender`, `org.apache.log4j.config`, `org.apache.log4j.helpers`
- … and 2 more

**Class cycles removed** (2):

- 3: `org.apache.log4j.LogManager`, `org.apache.log4j.Logger`, `org.apache.log4j.spi.RootLogger`
- 4: `org.apache.logging.log4j.internal.DefaultLogBuilder`, `org.apache.logging.log4j.spi.AbstractLogger`, `org.apache.logging.log4j.status.StatusLogger`, `org.apache.logging.log4j.util.StackLocatorUtil`

**Class cycles created** (1):

- 3: `org.apache.log4j.LogManager`, `org.apache.log4j.Logger`, `org.apache.log4j.helpers.RootLogger`

**Unstable dependencies removed** (1): `org.apache.log4j.spi` → `org.apache.log4j.helpers`

### log4j2-C5 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **714 → 725 (net +11)**
- smells removed: **44**, smells created: **55**
- package cycles 201 → 201, class cycles 380 → 390, unstable 130 → 131, hub-like 3 → 3

**Classes relocated** (1):

- `org.apache.logging.log4j.core.config.plugins.validation.constraints.Required`

**Package cycles removed** (1):

- 11: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.validation`, `org.apache.logging.log4j.core.config.plugins.validation.constraints` …

**Package cycles created** (1):

- 15: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.util`, `org.apache.logging.log4j.core.config.plugins.validation` …

**Class cycles removed** (43):

- 2: `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.RingBufferLogEvent`
- 3: `org.apache.logging.log4j.core.config.PropertiesPlugin`, `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`
- 3: `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.RingBufferLogEvent`, `org.apache.logging.log4j.core.async.RingBufferLogEventTranslator`
- 4: `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.AsyncLoggerDisruptor`, `org.apache.logging.log4j.core.async.RingBufferLogEvent`, `org.apache.logging.log4j.core.async.RingBufferLogEventHandler4`
- 4: `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.async.AsyncLoggerDisruptor`, `org.apache.logging.log4j.core.jmx.RingBufferAdmin`, `org.apache.logging.log4j.core.jmx.Server`
- 4: `org.apache.logging.log4j.core.config.PropertiesPlugin`, `org.apache.logging.log4j.core.config.Property`, `org.apache.logging.log4j.core.lookup.Interpolator`, `org.apache.logging.log4j.core.lookup.PropertiesLookup`
- 6: `org.apache.logging.log4j.core.LoggerContext`, `org.apache.logging.log4j.core.appender.AbstractManager`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.NullConfiguration`, `org.apache.logging.log4j.core.lookup.Interpolator` …
- 6: `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.async.AsyncLoggerDisruptor`, `org.apache.logging.log4j.core.config.LoggerConfig`, `org.apache.logging.log4j.core.jmx.LoggerConfigAdmin`, `org.apache.logging.log4j.core.jmx.RingBufferAdmin` …
- 6: `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.builder.api.ConfigurationBuilderFactory`, `org.apache.logging.log4j.core.config.builder.impl.BuiltConfiguration` …
- 6: `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.async.AsyncLoggerDisruptor`, `org.apache.logging.log4j.core.async.RingBufferLogEvent`, `org.apache.logging.log4j.core.async.RingBufferLogEventHandler4` …
- … and 33 more

**Class cycles created** (53):

- 3: `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.config.LoggerConfig`
- 3: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 4: `org.apache.logging.log4j.core.tools.Generate`, `org.apache.logging.log4j.core.tools.Generate$ExtendedLogger`, `org.apache.logging.log4j.core.tools.Generate$Type`, `org.apache.logging.log4j.core.tools.Generate$Type$2`
- 4: `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.DefaultConfiguration`, `org.apache.logging.log4j.core.config.LoggerConfig`
- 4: `org.apache.logging.log4j.core.config.ConfigurationFactory`, `org.apache.logging.log4j.core.config.ConfigurationFactory$Factory`, `org.apache.logging.log4j.core.config.ConfigurationSource`, `org.apache.logging.log4j.core.config.composite.CompositeConfiguration`
- 5: `org.apache.logging.log4j.core.async.AsyncLoggerConfigDisruptor`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.impl.Log4jContextFactory`, `org.apache.logging.log4j.core.jmx.RingBufferAdmin`, `org.apache.logging.log4j.core.jmx.Server`
- 5: `org.apache.logging.log4j.core.Logger`, `org.apache.logging.log4j.core.Logger$PrivateConfig`, `org.apache.logging.log4j.core.async.AsyncLogger`, `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.config.LoggerConfig`
- 5: `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.DefaultConfiguration`, `org.apache.logging.log4j.core.config.LoggerConfig`, `org.apache.logging.log4j.core.config.ReliabilityStrategyFactory`
- 6: `org.apache.logging.log4j.core.Logger`, `org.apache.logging.log4j.core.Logger$PrivateConfig`, `org.apache.logging.log4j.core.async.AsyncLoggerContext`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.DefaultConfiguration` …
- 6: `org.apache.logging.log4j.core.async.AsyncLoggerConfigDisruptor`, `org.apache.logging.log4j.core.config.AbstractConfiguration`, `org.apache.logging.log4j.core.config.DefaultConfiguration`, `org.apache.logging.log4j.core.impl.Log4jContextFactory`, `org.apache.logging.log4j.core.jmx.RingBufferAdmin` …
- … and 43 more

**Unstable dependencies created** (1): `org.apache.logging.log4j.core.config` → `org.apache.logging.log4j.core.config.plugins.validation`

### log4j2-C6 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **714 → 714 (net +0)**
- smells removed: **14**, smells created: **14**
- package cycles 201 → 201, class cycles 380 → 379, unstable 130 → 131, hub-like 3 → 3

**Classes relocated** (1):

- `org.apache.logging.log4j.core.config.plugins.validation.constraints.Required`

**Package cycles removed** (12):

- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.jmx`
- 5: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl`, `org.apache.logging.log4j.core.jmx`
- 9: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 10: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 11: `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.convert`, `org.apache.logging.log4j.core.config.plugins.util` …
- 11: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.validation`, `org.apache.logging.log4j.core.config.plugins.validation.constraints` …
- 11: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 13: `org.apache.logging.log4j`, `org.apache.logging.log4j.core`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter` …
- 14: `org.apache.logging.log4j`, `org.apache.logging.log4j.core`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter` …
- 16: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.appender.rolling.action`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.convert` …
- … and 2 more

**Package cycles created** (12):

- 3: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.script`
- 4: `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl`
- 8: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 9: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 9: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 10: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 10: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- 11: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.config.plugins.validation`, `org.apache.logging.log4j.core.filter` …
- 11: `org.apache.logging.log4j`, `org.apache.logging.log4j.core.async`, `org.apache.logging.log4j.core.config`, `org.apache.logging.log4j.core.filter`, `org.apache.logging.log4j.core.impl` …
- … and 2 more

**Class cycles removed** (1):

- 4: `org.apache.logging.log4j.internal.DefaultLogBuilder`, `org.apache.logging.log4j.spi.AbstractLogger`, `org.apache.logging.log4j.status.StatusLogger`, `org.apache.logging.log4j.util.StackLocatorUtil`

**Unstable dependencies removed** (1): `org.apache.log4j.xml` → `org.apache.logging.log4j.core.filter`

**Unstable dependencies created** (2): `org.apache.logging.log4j.core.filter` → `org.apache.logging.log4j.core.script`; `org.apache.logging.log4j.core.filter` → `org.apache.logging.log4j.core.util.internal`


---

## struts  (baseline 227 smells)

### struts-B4 — arm B, model suggestions

- moves applied: **25**
- Arcan total: **227 → 254 (net +27)**
- smells removed: **26**, smells created: **53**
- package cycles 87 → 104, class cycles 48 → 52, unstable 92 → 98, hub-like 0 → 0

**Classes relocated** (25):

- `org.apache.tiles.request.freemarker.FreemarkerRequestException`
- `org.apache.struts2.action.ServletContextAware`
- `org.apache.struts2.action.SessionAware`
- `org.apache.struts2.action.UploadedFilesAware`
- `org.apache.struts2.config.BeanSelectionProvider`
- `org.apache.struts2.config.ConfigurationUtil`
- `org.apache.struts2.config.entities.InterceptorStackConfig`
- `org.apache.struts2.config.impl.MockConfiguration`
- `org.apache.struts2.config.providers.InterceptorBuilder`
- `org.apache.struts2.factory.ResultFactory`
- `org.apache.struts2.interceptor.ModelDrivenInterceptor`
- `org.apache.struts2.interceptor.NoOpInterceptor`
- `org.apache.struts2.interceptor.PreResultListener`
- `org.apache.struts2.interceptor.csp.CspNonceReader`
- … and 11 more

**Package cycles removed** (16):

- 2: `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.util`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`
- 4: `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.factory`
- … and 6 more

**Package cycles created** (33):

- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.ognl.accessor`
- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 3: `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.ognl.accessor`
- 3: `org.apache.struts2.config.providers`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.config`, `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher.mapper`, `org.apache.struts2.result`
- 4: `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.multipart`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 5: `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`, `org.apache.struts2.validator`
- 5: `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.csp`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- … and 23 more

**Class cycles removed** (2):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`
- 3: `org.apache.struts2.ognl.OgnlUtil`, `org.apache.struts2.ognl.SecurityMemberAccess`, `org.apache.struts2.util.ConfigParseUtil`

**Class cycles created** (6):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.config.SecurityMemberAccess`, `org.apache.struts2.ognl.OgnlUtil`, `org.apache.struts2.util.ConfigParseUtil`
- 3: `org.apache.struts2.result.xslt.AdapterFactory`, `org.apache.struts2.result.xslt.ProxyAttrAdapter`, `org.apache.struts2.result.xslt.ProxyNodeAdapter`
- 3: `org.apache.struts2.result.xslt.AdapterFactory`, `org.apache.struts2.result.xslt.ProxyNodeAdapter`, `org.apache.struts2.result.xslt.ProxyTextNodeAdapter`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (8): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.components` → `org.apache.struts2.interceptor.csp`; `org.apache.struts2.config` → `org.apache.struts2.dispatcher`; `org.apache.struts2.config` → `org.apache.struts2.interceptor.csp`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter` …

**Unstable dependencies created** (14): `org.apache.struts2.action` → `org.apache.struts2`; `org.apache.struts2.config` → `org.apache.struts2.interceptor`; `org.apache.struts2.config.entities` → `org.apache.struts2.config`; `org.apache.struts2.config.providers` → `org.apache.struts2.interceptor.csp`; `org.apache.struts2.config.providers` → `org.apache.struts2.ognl.accessor`; `org.apache.struts2.config.providers` → `org.apache.struts2.util.fs` …

### struts-C1 — arm C, DSARP planner

- moves applied: **12**
- Arcan total: **227 → 227 (net +0)**
- smells removed: **55**, smells created: **55**
- package cycles 87 → 91, class cycles 48 → 49, unstable 92 → 87, hub-like 0 → 0

**Classes relocated** (12):

- `org.apache.struts2.action.CspSettingsAware`
- `org.apache.struts2.action.PrincipalAware`
- `org.apache.struts2.config.entities.BeanSelectionConfig`
- `org.apache.struts2.config.providers.StrutsDefaultConfigurationProvider`
- `org.apache.struts2.config.providers.XmlHelper`
- `org.apache.struts2.conversion.UploadedFileConverter`
- `org.apache.struts2.conversion.UploadedFileConverter`
- `org.apache.struts2.conversion.impl.ConversionData`
- `org.apache.struts2.dispatcher.DefaultActionSupport`
- `org.apache.struts2.interceptor.ActionMappingParametersInterceptor`
- `org.apache.struts2.interceptor.PrincipalProxy`
- `org.apache.struts2.interceptor.PrincipalProxy`

**Package cycles removed** (48):

- 2: `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 2: `org.apache.struts2.conversion`, `org.apache.struts2.conversion.impl`
- 2: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 2: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.servlet`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2.conversion`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.ognl`
- … and 38 more

**Package cycles created** (52):

- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`
- 2: `org.apache.struts2.config.impl`, `org.apache.struts2.ognl.accessor`
- 3: `org.apache.struts2.conversion.impl`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 3: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`
- 3: `org.apache.struts2.config.impl`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.csp`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 5: `org.apache.struts2.config.impl`, `org.apache.struts2.factory`, `org.apache.struts2.interceptor`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 5: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`, `org.apache.struts2.interceptor`, `org.apache.struts2.result`
- … and 42 more

**Class cycles created** (1):

- 3: `org.apache.struts2.util.location.LocationAttributes`, `org.apache.struts2.util.location.LocationImpl`, `org.apache.struts2.util.location.LocationUtils`

**Unstable dependencies removed** (7): `org.apache.struts2` → `org.apache.struts2.conversion.impl`; `org.apache.struts2.conversion` → `org.apache.struts2.conversion.impl`; `org.apache.struts2.conversion` → `org.apache.struts2.dispatcher.multipart`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor.servlet` → `org.apache.struts2.interceptor` …

**Unstable dependencies created** (2): `org.apache.struts2.ognl.accessor` → `org.apache.struts2.config.impl`; `org.apache.struts2.util` → `org.apache.struts2.ognl.accessor`

### struts-C2 — arm C, DSARP planner

- moves applied: **12**
- Arcan total: **227 → 212 (net -15)**
- smells removed: **24**, smells created: **9**
- package cycles 87 → 75, class cycles 48 → 48, unstable 92 → 89, hub-like 0 → 0

**Classes relocated** (12):

- `org.apache.struts2.interceptor.ServletConfigInterceptor`
- `org.apache.struts2.interceptor.annotations.InputConfig`
- `org.apache.struts2.interceptor.csp.CspInterceptor`
- `org.apache.struts2.interceptor.csp.CspInterceptor`
- `org.apache.struts2.interceptor.csp.CspSettings`
- `org.apache.struts2.interceptor.servlet.ServletPrincipalProxy`
- `org.apache.struts2.ognl.accessor.RootAccessor`
- `org.apache.struts2.ognl.accessor.RootAccessor`
- `org.apache.struts2.util.PrefixTrie`
- `org.apache.struts2.validator.DefaultValidatorFileParser`
- `org.apache.struts2.views.DefaultTagLibrary`
- `org.apache.struts2.views.jsp.IteratorStatus`

**Package cycles removed** (16):

- 2: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.annotations`
- 2: `org.apache.struts2.components`, `org.apache.struts2.views.jsp`
- 2: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.servlet`
- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 2: `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`
- 3: `org.apache.struts2.components`, `org.apache.struts2.config`, `org.apache.struts2.views.jsp`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`
- 4: `org.apache.struts2`, `org.apache.struts2.components`, `org.apache.struts2.config`, `org.apache.struts2.views.jsp`
- 5: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`, `org.apache.struts2.util`
- … and 6 more

**Package cycles created** (4):

- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.interceptor.csp`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.interceptor.csp`, `org.apache.struts2.util`
- 5: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.ognl.accessor`
- 6: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.ognl.accessor` …

**Unstable dependencies removed** (8): `org.apache.struts2.components` → `org.apache.struts2.views.jsp`; `org.apache.struts2.config` → `org.apache.struts2.dispatcher`; `org.apache.struts2.config` → `org.apache.struts2.ognl.accessor`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.annotations`; `org.apache.struts2.interceptor.servlet` → `org.apache.struts2.interceptor`; `org.apache.struts2.ognl` → `org.apache.struts2.ognl.accessor` …

**Unstable dependencies created** (5): `org.apache.struts2.components` → `org.apache.struts2.util`; `org.apache.struts2.config` → `org.apache.struts2.interceptor`; `org.apache.struts2.config.impl` → `org.apache.struts2.ognl.accessor`; `org.apache.struts2.config.providers` → `org.apache.struts2.ognl.accessor`; `org.apache.struts2.dispatcher` → `org.apache.struts2.config`

### struts-C4 — arm C, DSARP planner

- moves applied: **12**
- Arcan total: **227 → 235 (net +8)**
- smells removed: **56**, smells created: **64**
- package cycles 87 → 97, class cycles 48 → 52, unstable 92 → 86, hub-like 0 → 0

**Classes relocated** (12):

- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.config.StrutsBeanSelectionProvider`
- `org.apache.struts2.conversion.TypeConverter`
- `org.apache.struts2.ognl.StrutsOgnlGuard`
- `org.apache.struts2.test.StubConfigurationProvider`
- `org.apache.struts2.test.StubConfigurationProvider`

**Package cycles removed** (34):

- 2: `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 2: `org.apache.struts2.components`, `org.apache.struts2.config`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.conversion`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.ognl`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.interceptor.csp`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.components`, `org.apache.struts2.config`, `org.apache.struts2.views.jsp`
- 3: `org.apache.struts2`, `org.apache.struts2.components`, `org.apache.struts2.config`
- 4: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.util`
- … and 24 more

**Package cycles created** (44):

- 2: `org.apache.struts2.components`, `org.apache.struts2.dispatcher`
- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 3: `org.apache.struts2.components`, `org.apache.struts2.dispatcher`, `org.apache.struts2.views.jsp`
- 3: `org.apache.struts2.components`, `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`
- 4: `org.apache.struts2.components`, `org.apache.struts2.config.providers`, `org.apache.struts2.dispatcher`, `org.apache.struts2.validator`
- 4: `org.apache.struts2.conversion`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.ognl`, `org.apache.struts2.ognl.accessor`
- 4: `org.apache.struts2.components`, `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`
- 4: `org.apache.struts2.components`, `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.validator`
- 5: `org.apache.struts2.components`, `org.apache.struts2.config.entities`, `org.apache.struts2.config.providers`, `org.apache.struts2.dispatcher`, `org.apache.struts2.validator`
- 6: `org.apache.struts2.components`, `org.apache.struts2.config.entities`, `org.apache.struts2.config.impl`, `org.apache.struts2.config.providers`, `org.apache.struts2.dispatcher` …
- … and 34 more

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (5):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.result.xslt.AdapterFactory`, `org.apache.struts2.result.xslt.ProxyAttrAdapter`, `org.apache.struts2.result.xslt.ProxyNodeAdapter`
- 3: `org.apache.struts2.result.xslt.AdapterFactory`, `org.apache.struts2.result.xslt.ProxyNodeAdapter`, `org.apache.struts2.result.xslt.ProxyTextNodeAdapter`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (21): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.components` → `org.apache.struts2.components.template`; `org.apache.struts2.components` → `org.apache.struts2.config`; `org.apache.struts2.config` → `org.apache.struts2.components.date`; `org.apache.struts2.config` → `org.apache.struts2.conversion.impl`; `org.apache.struts2.config` → `org.apache.struts2.dispatcher` …

**Unstable dependencies created** (15): `org.apache.struts2.action` → `org.apache.struts2`; `org.apache.struts2.components` → `org.apache.struts2.conversion.impl`; `org.apache.struts2.components` → `org.apache.struts2.dispatcher.multipart`; `org.apache.struts2.components` → `org.apache.struts2.factory`; `org.apache.struts2.components` → `org.apache.struts2.interceptor.exec`; `org.apache.struts2.components` → `org.apache.struts2.ognl.accessor` …

### struts-C5 — arm C, DSARP planner

- moves applied: **3**
- Arcan total: **227 → 249 (net +22)**
- smells removed: **72**, smells created: **94**
- package cycles 87 → 105, class cycles 48 → 50, unstable 92 → 94, hub-like 0 → 0

**Classes relocated** (3):

- `org.apache.struts2.test.StubConfigurationProvider`
- `org.apache.struts2.util.fs.DefaultFileManagerFactory`
- `org.apache.struts.beanvalidation.constraints.FieldMatch`

**Package cycles removed** (66):

- 2: `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 2: `org.apache.struts2.components`, `org.apache.struts2.config`
- 2: `org.apache.struts2`, `org.apache.struts2.config`
- 2: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`
- 3: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.result`
- 3: `org.apache.struts2.conversion`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.ognl`
- 3: `org.apache.struts2.components`, `org.apache.struts2.config`, `org.apache.struts2.views.jsp`
- … and 56 more

**Package cycles created** (84):

- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 2: `org.apache.struts2.config`, `org.apache.struts2.dispatcher`
- 2: `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.multipart`
- 2: `org.apache.struts2.text`, `org.apache.struts2.util`
- 2: `org.apache.struts2`, `org.apache.struts2.interceptor`
- 2: `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 2: `org.apache.struts2.components`, `org.apache.struts2.components.template`
- 3: `org.apache.struts2`, `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 3: `org.apache.struts2`, `org.apache.struts2.text`, `org.apache.struts2.util`
- … and 74 more

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (3):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (5): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.test` → `org.apache.struts2.config`

**Unstable dependencies created** (7): `org.apache.struts2.action` → `org.apache.struts2`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.dispatcher`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.ognl`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.security`; `org.apache.struts2.interceptor.validation` → `org.apache.struts2.validator` …

### struts-C7 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **227 → 251 (net +24)**
- smells removed: **76**, smells created: **100**
- package cycles 87 → 107, class cycles 48 → 50, unstable 92 → 94, hub-like 0 → 0

**Classes relocated** (1):

- `org.apache.struts2.interceptor.Interceptor`

**Package cycles removed** (69):

- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 2: `org.apache.struts2.components`, `org.apache.struts2.config`
- 2: `org.apache.struts2`, `org.apache.struts2.config`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor.parameter`
- 2: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`
- 3: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.result`
- … and 59 more

**Package cycles created** (89):

- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 2: `org.apache.struts2.config`, `org.apache.struts2.dispatcher`
- 2: `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.multipart`
- 2: `org.apache.struts2.text`, `org.apache.struts2.util`
- 2: `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 2: `org.apache.struts2.components`, `org.apache.struts2.components.template`
- 3: `org.apache.struts2`, `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 3: `org.apache.struts2`, `org.apache.struts2.text`, `org.apache.struts2.util`
- 3: `org.apache.struts2`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- … and 79 more

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (3):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (6): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.annotations`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.parameter`

**Unstable dependencies created** (8): `org.apache.struts2.action` → `org.apache.struts2`; `org.apache.struts2.interceptor.annotations` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.dispatcher`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.ognl`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.security` …

### struts-C8 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **227 → 253 (net +26)**
- smells removed: **77**, smells created: **103**
- package cycles 87 → 108, class cycles 48 → 50, unstable 92 → 95, hub-like 0 → 0

**Classes relocated** (1):

- `org.apache.struts2.interceptor.Interceptor`

**Package cycles removed** (69):

- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 2: `org.apache.struts2.components`, `org.apache.struts2.config`
- 2: `org.apache.struts2`, `org.apache.struts2.config`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor.parameter`
- 2: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`
- 3: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.result`
- … and 59 more

**Package cycles created** (90):

- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 2: `org.apache.struts2.config`, `org.apache.struts2.dispatcher`
- 2: `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.multipart`
- 2: `org.apache.struts2.text`, `org.apache.struts2.util`
- 2: `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 2: `org.apache.struts2.components`, `org.apache.struts2.components.template`
- 3: `org.apache.struts2`, `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 3: `org.apache.struts2`, `org.apache.struts2.text`, `org.apache.struts2.util`
- 3: `org.apache.struts2`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- … and 80 more

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (3):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (7): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.config` → `org.apache.struts2.dispatcher`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.annotations` …

**Unstable dependencies created** (10): `org.apache.struts2` → `org.apache.struts2.dispatcher`; `org.apache.struts2.action` → `org.apache.struts2`; `org.apache.struts2.dispatcher` → `org.apache.struts2.config`; `org.apache.struts2.interceptor.annotations` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.dispatcher`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.interceptor` …

### struts-C9 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **227 → 232 (net +5)**
- smells removed: **5**, smells created: **10**
- package cycles 87 → 88, class cycles 48 → 50, unstable 92 → 94, hub-like 0 → 0

**Classes relocated** (1):

- `org.apache.struts2.action.Action`

**Package cycles created** (1):

- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (3):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (4): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.parameter`

**Unstable dependencies created** (6): `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.dispatcher`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.ognl`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.security`; `org.apache.struts2.interceptor.validation` → `org.apache.struts2.validator`; `org.apache.struts2.showcase.dao` → `org.apache.struts2.showcase.application`

### struts-C10 — arm C, DSARP planner

- moves applied: **1**
- Arcan total: **227 → 251 (net +24)**
- smells removed: **74**, smells created: **98**
- package cycles 87 → 107, class cycles 48 → 50, unstable 92 → 94, hub-like 0 → 0

**Classes relocated** (1):

- `org.apache.struts2.action.Action`

**Package cycles removed** (69):

- 2: `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 2: `org.apache.struts2.components`, `org.apache.struts2.config`
- 2: `org.apache.struts2`, `org.apache.struts2.config`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor.parameter`
- 2: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`
- 3: `org.apache.struts2.config.entities`, `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.mapper`
- 3: `org.apache.struts2.config`, `org.apache.struts2.config.providers`, `org.apache.struts2.validator`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.config.providers`
- 3: `org.apache.struts2.dispatcher`, `org.apache.struts2.interceptor`, `org.apache.struts2.interceptor.parameter`
- 3: `org.apache.struts2`, `org.apache.struts2.config`, `org.apache.struts2.result`
- … and 59 more

**Package cycles created** (89):

- 2: `org.apache.struts2.showcase.application`, `org.apache.struts2.showcase.dao`
- 2: `org.apache.struts2.config`, `org.apache.struts2.dispatcher`
- 2: `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- 2: `org.apache.struts2.dispatcher`, `org.apache.struts2.dispatcher.multipart`
- 2: `org.apache.struts2.text`, `org.apache.struts2.util`
- 2: `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 2: `org.apache.struts2.components`, `org.apache.struts2.components.template`
- 3: `org.apache.struts2`, `org.apache.struts2.util`, `org.apache.struts2.views.util`
- 3: `org.apache.struts2`, `org.apache.struts2.text`, `org.apache.struts2.util`
- 3: `org.apache.struts2`, `org.apache.struts2.conversion.impl`, `org.apache.struts2.util`
- … and 79 more

**Class cycles removed** (1):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$CookieLocaleHandler`

**Class cycles created** (3):

- 2: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 3: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`
- 4: `org.apache.struts2.interceptor.I18nInterceptor`, `org.apache.struts2.interceptor.I18nInterceptor$AcceptLanguageLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$RequestLocaleHandler`, `org.apache.struts2.interceptor.I18nInterceptor$SessionLocaleHandler`

**Unstable dependencies removed** (4): `org.apache.struts2` → `org.apache.struts2.action`; `org.apache.struts2.conversion` → `org.apache.struts2.util`; `org.apache.struts2.dispatcher` → `org.apache.struts2.interceptor.parameter`; `org.apache.struts2.interceptor` → `org.apache.struts2.interceptor.parameter`

**Unstable dependencies created** (6): `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.dispatcher`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.interceptor`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.ognl`; `org.apache.struts2.interceptor.parameter` → `org.apache.struts2.security`; `org.apache.struts2.interceptor.validation` → `org.apache.struts2.validator`; `org.apache.struts2.showcase.dao` → `org.apache.struts2.showcase.application`
