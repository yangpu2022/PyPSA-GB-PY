# Manual

A guide to PyPSA-GB in three layers, from the whole model on one page down to the modules that implement each part.
Read down as far as your question needs: most users stop at the second layer; the third is for changing the code.

| Layer | Answers | Pages |
|---|---|---|
| 1. {doc}`overview` | What the model is, what goes in and what comes out, and the order things happen in | one page |
| 2. {doc}`subsystems/index` | What each part of the model does, which rules run it, which files it reads and writes, and which settings change it | one page per part |
| 3. {doc}`modules/index` | Which module does what, the functions to start from, and the conventions a change must keep | one page per package |
| {doc}`notebooks/index` | The ideas of layers 2 and 3 run on small networks, with the model's own functions | three notebooks |

Each page links up to the layer above and down to the layer below, and across to the {doc}`/model/index` chapter
that gives the method, data and validation in full. The manual does not repeat those chapters: it is the map, they
are the territory.

## Reading paths

| If you want to | Read |
|---|---|
| run a scenario and read its results | {doc}`overview`, then {doc}`/getting_started/index` |
| understand why a result came out as it did | {doc}`overview`, the layer 2 page of the part concerned, then its {doc}`/model/index` chapter |
| change a setting | {doc}`subsystems/configuration`, then the "Settings" table of the part concerned |
| change or add code | the part's layer 2 page, its layer 3 page, and {doc}`/development/index` |
| see the market and the buses at work without a full run | {doc}`notebooks/index` |

```{toctree}
:maxdepth: 2
:hidden:

overview
subsystems/index
modules/index
notebooks/index
```
