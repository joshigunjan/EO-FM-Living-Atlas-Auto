# EO-FM Living Atlas

The **EO-FM Living Atlas** is an interactive, continuously updated catalogue of foundation models, benchmarks, and datasets for Earth observation and remote sensing.

It brings together information that is otherwise scattered across papers, project pages, model repositories, and community-maintained lists, and presents it through a searchable catalogue, interactive landscape, benchmark timeline, and model-detail views.

## Explore the atlas

The website includes:

- A searchable catalogue of Earth observation foundation models
- Filters for year, modality, architecture, modelling paradigm, access, and downstream tasks
- An interactive landscape showing the progression of the field
- A benchmark and dataset catalogue with publication years
- Model-detail pages with paper, code, weights, and project links
- A concise methodology page explaining how entries are collected and structured
- An add-entry page for community contributions

## Why this project exists

The Earth observation foundation-model landscape is growing quickly, but information about new models is often fragmented across papers, GitHub repositories, Hugging Face pages, technical reports, and survey lists.

The EO-FM Living Atlas aims to make this information easier to:

- discover
- compare
- explore over time
- trace back to primary sources
- maintain as the field evolves

The atlas is intended as a living research resource rather than a static survey table.

## How the catalogue is updated

The repository combines automated discovery with curated reference records.

```text
Public EO and remote-sensing model lists
        ↓
Model, benchmark, and dataset extraction
        ↓
Deduplication using DOI, arXiv, paper, GitHub, and Hugging Face links
        ↓
Metadata collection from primary sources
        ↓
Structured enrichment of modalities, architecture, tasks, access, and training details
        ↓
Classification into models, benchmarks, datasets, and related resources
        ↓
Automatic update of the website and interactive landscape
```

Reviewed entries take precedence over weaker automatically inferred records. Distinct model releases are kept separate when they represent meaningful new versions, such as `Prithvi-EO-1.0` and `Prithvi-EO-2.0`.

## Catalogue structure

### Models

`data/catalogue.json`

Contains the model catalogue used by the Catalogue and Landscape pages.

Each entry may include:

- model name and release year
- scientific scope
- input modalities and sensors
- architecture
- modelling paradigm
- downstream tasks
- training scale
- access status
- paper, code, weights, and project links

### Benchmarks and datasets

`data/benchmarks.json`

Contains benchmark, evaluation, pretraining, and dataset records shown in the Benchmarks tab.

The benchmark timeline makes it possible to see how evaluation resources have evolved alongside the model landscape.

### Supporting data

```text
data/metadata.json
data/candidates/
data/manual_seed_catalogue.json
```

These files contain generation metadata, automatically collected candidate records, duplicate reports, and curated reference entries.

## Architecture and modelling paradigm

The atlas distinguishes between:

- **Architecture**: the structural design of the model, such as a Vision Transformer, CNN, state-space model, multimodal transformer, or encoder-decoder.
- **Modelling paradigm**: the learning strategy or functional role of the model, such as masked reconstruction, contrastive learning, vision-language alignment, autoregressive modelling, or generative multimodal learning.

A model may share the same architecture with another model while using a different modelling paradigm.

## Deduplication

Entries are merged only when strong evidence indicates that they refer to the same resource.

Strong matching evidence includes:

- identical DOI
- identical arXiv identifier
- identical paper URL
- identical GitHub repository
- identical Hugging Face repository
- identical project page

Name-only matches are not merged automatically, helping prevent separate releases from being collapsed into one entry.

## Publication rules

The public model catalogue is reserved for actual model or model-family entries.

Benchmarks and datasets are routed to the benchmark catalogue. Surveys, reviews, commentary papers, paper-only methods, and uncertain records remain in the candidate data for further inspection.

This separation helps keep the public atlas focused while preserving broader upstream coverage.

## Data quality

The atlas combines reviewed records with automatically structured entries.

Automated records are useful for discovery, but some fields may remain incomplete when primary sources do not clearly report modalities, architecture, tasks, training scale, or access conditions.

The atlas should therefore be used as a navigation and comparison resource. Important scientific claims should always be verified against the linked paper, model card, repository, or project page.

## Automation

The catalogue is rebuilt through GitHub Actions:

- whenever relevant changes are pushed to `main`
- automatically on the 1st and 15th of each month

The workflow updates the model catalogue, benchmark catalogue, metadata, and website data.

## Contributing

Contributions are welcome.

You can suggest:

- a new model
- a missing model release
- a benchmark or dataset
- a correction to an existing entry
- a paper, code, weights, or project link
- an update to modality, architecture, task, or access information

Please use the website's add-entry page or open an issue in this repository.

## Scope

The EO-FM Living Atlas focuses on foundation models and broadly reusable pretrained systems for:

- Earth observation
- remote sensing
- geospatial AI
- multimodal geospatial learning
- vision-language and agentic EO systems
- large-scale representation learning for geospatial data

The project does not rank models by performance. Its purpose is to document and organize the field.
