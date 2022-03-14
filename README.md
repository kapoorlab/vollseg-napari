# VollSeg Napari Plugin

[![PyPI version](https://img.shields.io/pypi/v/vollseg-napari.svg)](https://pypi.org/project/vollseg-napari)


This project provides the [napari](https://napari.org/) plugin for [VollSeg](https://github.com/kapoorlab/vollseg), a deep learning based 2D and 3D segmentation tool for irregular shaped cells. VollSeg has originally been developed (see [papers](http://conference.scipy.org/proceedings/scipy2021/varun_kapoor.html)) for the segmentation of densely packed membrane labelled cells in challenging images with low signal-to-noise ratios. The plugin allows to apply pretrained and custom trained models from within napari.



## Installation & Usage

Install the plugin with `pip install vollseg-napari` or from within napari via `Plugins > Install/Uninstall Package(s)…`. If you want GPU-accelerated prediction, please read the more detailed [installation instructions](https://github.com/kapoorlab/vollseg-napari#gpu_installation) for VollSeg.

You can activate the plugin in napari via `Plugins > VollSeg: VollSeg`. Example images for testing are provided via `File > Open Sample > VollSeg`.

If you use this plugin for your research, please [cite us](http://conference.scipy.org/proceedings/scipy2021/varun_kapoor.html).

## GPU_Installation

This package is compatible with Python 3.6 - 3.9.

1. Please first [install TensorFlow](https://www.tensorflow.org/install)
(TensorFlow 2) by following the official instructions.
For [GPU support](https://www.tensorflow.org/install/gpu), it is very
important to install the specific versions of CUDA and cuDNN that are
compatible with the respective version of TensorFlow. (If you need help and can use `conda`, take a look at [this](https://github.com/CSBDeep/CSBDeep/tree/master/extras#conda-environment).)

2. *VollSeg* can then be installed with `pip`:

    - If you installed TensorFlow 2 (version *2.x.x*):

          pip install vollseg


## Examples

VollSeg comes with different options to combine CARE based denoising with UNET, StarDist and segmentation in a region of interest (ROI). We present some examples which are represent optimal combination of these different modes for segmenting different cell types. We summarize this in the table below:

| Example Image | Description | Training Data | Trained Model | GT image   | Optimal combination  | Notebook Code | Model Prediction | Metrics |
| :-- | :-: | :-:| :-:| :--: | :--: | :-: | :--: | :-- |
| ![](https://github.com/kapoorlab/vollseg-napari/tree/main/vollseg_napari/resources/Ascadian_raw.jpg)| Light sheet fused from four angles 3D single channel| [Training Data ~320 GB](https://figshare.com/articles/dataset/Astec-half-Pm1_Cut_at_2-cell_stage_half_Phallusia_mammillata_embryo_live_SPIM_imaging_stages_6-16_/11309570?backTo=/s/765d4361d1b073beedd5)| [UNET model](https://zenodo.org/record/6337699) |<img src="https://github.com/kapoorlab/vollseg-napari/tree/main/vollseg_napari/resources/Ascadian_GT.jpg" title="GT Ascadian Embryo" width="120px" align="center"> | UNET model, slice_merge = False | [Colab Notebook](https://github.com/kapoorlab/VollSeg/blob/main/examples/Predict/Colab_VollSeg_Ascadian_Embryo.ipynb) |<img src="https://github.com/kapoorlab/vollseg-napari/tree/main/vollseg_napari/resources/Ascadian_pred.jpg" title="GT Ascadian Embryo" width="120px" align="center"> | <img src="https://github.com/kapoorlab/vollseg-napari/tree/main/vollseg_napari/resources/Metrics_Ascadian.jpg" title="Metrics Ascadian Embryo" width="120px" align="center">  |

## Troubleshooting & Support

- The [image.sc forum](https://forum.image.sc/tag/vollseg) is the best place to start getting help and support. Make sure to use the tag `vollseg`, since we are monitoring all questions with this tag.
- If you have technical questions or found a bug, feel free to [open an issue](https://github.com/kapoorlab/vollseg-napari/issues).

