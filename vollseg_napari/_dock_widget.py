# -*- coding: utf-8 -*-
'''
Created on Wed Dec  8 16:15:34 2021

@author: vkapoor
'''
from napari_plugin_engine import napari_hook_implementation
from magicgui import magicgui
from magicgui import widgets as mw
from magicgui.events import Event, Signal
from magicgui.application import use_app
import napari
from napari.qt.threading import thread_worker
from napari.utils.colormaps import label_colormap
from typing import List, Union
import functools
import time
from napari.layers import Image, Shapes
from enum import Enum
import numpy as np
from pathlib import Path
from warnings import warn
from tifffile import imread, imwrite
from vollseg import inrimage, h5, spatial_image
from qtpy.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QGridLayout,
    QListWidget,
    QPushButton,
    QFileDialog,
    QTabWidget,
    QLabel,
    QLineEdit,
    QScrollArea,
    QCheckBox,
    QSpinBox,
    QSizePolicy,
)


def plugin_wrapper_vollseg():

    from csbdeep.utils import _raise, normalize, axes_check_and_normalize, axes_dict
    from vollseg.pretrained import get_registered_models, get_model_folder, get_model_details, get_model_instance
    from csbdeep.utils import load_json
    import sys
    from vollseg import StarDist2D, StarDist3D
    from vollseg import VollSeg3D, VollSeg2D, VollSeg_unet
    from csbdeep.models import Config, CARE
    from vollseg import UNET

    from stardist.utils import abspath

    DEBUG = True
                
    def get_data(image):
        image = image.data[0] if image.multiscale else image.data
        # enforce dense numpy array in case we are given a dask array etc
        return np.asarray(image)

    def change_handler(*widgets, init=True, debug=DEBUG):
        def decorator_change_handler(handler):
            @functools.wraps(handler)
            def wrapper(*args):
                source = Signal.sender()
                emitter = Signal.current_emitter()
                if debug:
                    # print(f'{emitter}: {source} = {args!r}')
                    print(f'{str(emitter.name).upper()}: {source.name} = {args!r}')
                return handler(*args)

            for widget in widgets:
                widget.changed.connect(wrapper)
                if init:
                    widget.changed(widget.value)
            return wrapper

        return decorator_change_handler

    # get available models
    _models2d_star, _aliases2d_star = get_registered_models(StarDist2D)

    _models3d_star, _aliases3d_star = get_registered_models(StarDist3D)

    # use first alias for model selection (if alias exists)
    models2d_star = [
        ((_aliases2d_star[m][0] if len(_aliases2d_star[m]) > 0 else m), m)
        for m in _models2d_star
    ]
    models3d_star = [
        ((_aliases3d_star[m][0] if len(_aliases3d_star[m]) > 0 else m), m)
        for m in _models3d_star
    ]

    _models_unet, _aliases_unet = get_registered_models(UNET)
    # use first alias for model selection (if alias exists)
    models_unet = [
        ((_aliases_unet[m][0] if len(_aliases_unet[m]) > 0 else m), m)
        for m in _models_unet
    ]
    _models_den, _aliases_den = get_registered_models(CARE)
    # use first alias for model selection (if alias exists)
    models_den = [
        ((_aliases_den[m][0] if len(_aliases_den[m]) > 0 else m), m)
        for m in _models_den
    ]

    model_star_configs = dict()
    model_unet_configs = dict()
    model_den_configs = dict()
    model_star_threshs = dict()
    model_selected_star = None
    model_selected_unet = None
    model_selected_den = None

    CUSTOM_SEG_MODEL_STAR = 'CUSTOM_SEG_MODEL_STAR'
    CUSTOM_SEG_MODEL_UNET = 'CUSTOM_SEG_MODEL_UNET'
    CUSTOM_DEN_MODEL = 'CUSTOM_DEN_MODEL'
    star_seg_model_type_choices = [
        ('2D', StarDist2D),
        ('3D', StarDist3D),
        ('NOSTAR', 'NOSTAR'),
        ('Custom STAR', CUSTOM_SEG_MODEL_STAR),
    ]
    unet_seg_model_type_choices = [
        ('PreTrained', UNET),
        ('NOUNET', 'NOUNET'),
        ('Custom UNET', CUSTOM_SEG_MODEL_UNET),
    ]
    den_model_type_choices = [
        ('DenoiseCARE', CARE),
        ('NODEN', 'NODEN'),
        ('Custom CARE', CUSTOM_DEN_MODEL),
    ]

    @functools.lru_cache(maxsize=None)
    def get_model_star(star_seg_model_type, model_star):
        print(star_seg_model_type)
        if star_seg_model_type == CUSTOM_SEG_MODEL_STAR:
            path_star = Path(model_star)
            path_star.is_dir() or _raise(
                FileNotFoundError(f'{path_star} is not a directory')
            )
            config_star = model_star_configs[(star_seg_model_type, model_star)]
            model_class_star = StarDist2D if config_star['n_dim'] == 2 else StarDist3D
            return model_class_star(
                None, name=path_star.name, basedir=str(path_star.parent)
            )
       
        elif star_seg_model_type is not None:
            return star_seg_model_type.local_from_pretrained(model_star)
        else:
            
            return None

    @functools.lru_cache(maxsize=None)
    def get_model_unet(unet_seg_model_type, model_unet):
        if unet_seg_model_type == CUSTOM_SEG_MODEL_UNET:
            path_unet = Path(model_unet)
            path_unet.is_dir() or _raise(
                FileNotFoundError(f'{path_unet} is not a directory')
            )
            config_unet = model_unet_configs[(unet_seg_model_type, model_unet)]
            model_class_unet = UNET
            return model_class_unet(
                None, name=path_unet.name, basedir=str(path_unet.parent)
            )
        

        elif unet_seg_model_type is not None:
            return unet_seg_model_type.local_from_pretrained(model_unet)
        else:
            
            return None

    @functools.lru_cache(maxsize=None)
    def get_model_den(den_model_type, model_den):
        if den_model_type == CUSTOM_DEN_MODEL:
            path_den = Path(model_den)
            path_den.is_dir() or _raise(
                FileNotFoundError(f'{path_den} is not a directory')
            )
            model_class_den = CARE
            return model_class_den(
                None, name=path_den.name, basedir=str(path_den.parent)
            )
        elif den_model_type == CARE:
            return den_model_type.local_from_pretrained(model_den)

        elif den_model_type == 'NODEN':
            return None

    class Output(Enum):
        Labels = 'Label Image'
        Binary_mask = 'Binary Image'
        Skeleton_mask = 'Skeleton Image'
        Denoised_image = 'Denoised Image'
        Prob = 'Probability Map'
        Markers = 'Markers'
        All = 'All'

    output_choices = [
        Output.Labels.value,
        Output.Binary_mask.value,
        Output.Skeleton_mask.value,
        Output.Denoised_image.value,
        Output.Prob.value,
        Output.Markers.value,
        Output.All.value,
    ]

    DEFAULTS_MODEL = dict(
        star_seg_model_type=StarDist3D,
        unet_seg_model_type=UNET,
        den_model_type=CARE,
        model2d_star=models2d_star[0][0],
        model_unet=models_unet[0][0],
        model3d_star=models3d_star[0][0],
        model_den=models_den[0][0],
        model_den_none='NODEN',
        model_star_none='NOSTAR',
        model_unet_none='NOUNET',
        norm_axes='ZYX',
    )

    DEFAULTS_STAR_PARAMETERS = dict(
        norm_image=True,
        perc_low=1.0,
        perc_high=99.8,
        prob_thresh=0.5,
        nms_thresh=0.4,
        n_tiles=(1,1,1),
    )

    DEFAULTS_VOLL_PARAMETERS = dict(
        min_size_mask=100.0,
        min_size=100.0,
        max_size=10000.0,
        isRGB = False,
        dounet=True,
        slicemerge = False,
        iouthresh = 0.5,
        prob_map_watershed=True,
    )

    @magicgui(
        norm_image=dict(
            widget_type='CheckBox',
            text='Normalize Image',
            value=DEFAULTS_STAR_PARAMETERS['norm_image'],
        ),
        perc_low=dict(
            widget_type='FloatSpinBox',
            label='Percentile low',
            min=0.0,
            max=100.0,
            step=0.1,
            value=DEFAULTS_STAR_PARAMETERS['perc_low'],
        ),
        perc_high=dict(
            widget_type='FloatSpinBox',
            label='Percentile high',
            min=0.0,
            max=100.0,
            step=0.1,
            value=DEFAULTS_STAR_PARAMETERS['perc_high'],
        ),
        prob_thresh=dict(
            widget_type='FloatSpinBox',
            label='Probability/Score Threshold',
            min=0.0,
            max=1.0,
            step=0.05,
            value=DEFAULTS_STAR_PARAMETERS['prob_thresh'],
        ),
        nms_thresh=dict(
            widget_type='FloatSpinBox',
            label='Overlap Threshold',
            min=0.0,
            max=1.0,
            step=0.05,
            value=DEFAULTS_STAR_PARAMETERS['nms_thresh'],
        ),
        set_thresholds=dict(
            widget_type='PushButton',
            text='Set optimized postprocessing thresholds (for selected model)',
        ),
        n_tiles=dict(
            widget_type='LiteralEvalLineEdit',
            label='Number of Tiles',
            value=DEFAULTS_STAR_PARAMETERS['n_tiles'],
        ),
        defaults_star_parameters_button=dict(
            widget_type='PushButton', text='Restore StarDist Parameter Defaults'
        ),
        call_button=False,
    )
    def plugin_star_parameters(
        norm_image,
        perc_low,
        perc_high,
        prob_thresh,
        nms_thresh,
        set_thresholds,
        n_tiles,
        defaults_star_parameters_button
        
    ):

        return plugin_star_parameters

    @magicgui(
        min_size_mask=dict(
            widget_type='FloatSpinBox',
            label='Min Size Mask (px)',
            min=0.0,
            max=1000.0,
            step=1,
            value=DEFAULTS_VOLL_PARAMETERS['min_size_mask'],
        ),
        min_size=dict(
            widget_type='FloatSpinBox',
            label='Min Size Cells (px)',
            min=0.0,
            max=1000.0,
            step=1,
            value=DEFAULTS_VOLL_PARAMETERS['min_size'],
        ),
        max_size=dict(
            widget_type='FloatSpinBox',
            label='Max Size Cells (px)',
            min=1000,
            max=100000.0,
            step=100,
            value=DEFAULTS_VOLL_PARAMETERS['max_size'],
        ),
        
        prob_map_watershed=dict(
            widget_type='CheckBox',
            text='Use Probability Map (watershed)',
            value=DEFAULTS_VOLL_PARAMETERS['prob_map_watershed'],
        ),
        dounet=dict(
            widget_type='CheckBox',
            text='Use UNET for binary mask (else denoised)',
            value=DEFAULTS_VOLL_PARAMETERS['dounet'],
        ),
        isRGB=dict(
            widget_type='CheckBox',
            text='RGB image',
            value=DEFAULTS_VOLL_PARAMETERS['isRGB'],
        ),
        slicemerge=dict(
            widget_type='CheckBox',
            text='Merge slices (UNET)',
            value=DEFAULTS_VOLL_PARAMETERS['slicemerge'],
        ),
        iouthresh=dict(
            widget_type='FloatSpinBox',
            label='Threshold linkining',
            min=0,
            max=10,
            step=0.1,
            value=DEFAULTS_VOLL_PARAMETERS['iouthresh'],
        ),
        defaults_vollseg_parameters_button=dict(
            widget_type='PushButton', text='Restore VollSeg Parameter Defaults'
        ),
        
        call_button=False,
    )
    def plugin_extra_parameters(
        min_size_mask,
        min_size,
        max_size,
        prob_map_watershed,
        dounet,
        isRGB,
        slicemerge,
        iouthresh,
        defaults_vollseg_parameters_button,
        
    ):

        return plugin_extra_parameters

    logo = abspath(__file__, 'resources/vollseg_logo_napari.png')

    @magicgui(
        label_head=dict(
            widget_type='Label', label=f'<h1><img src="{logo}">VollSeg</h1>'
        ),
        image=dict(label='Input Image'),
        axes=dict(widget_type='LineEdit', label='Image Axes'),
        star_seg_model_type=dict(
            widget_type='RadioButtons',
            label='StarDist Model Type',
            orientation='horizontal',
            choices=star_seg_model_type_choices,
            value=DEFAULTS_MODEL['star_seg_model_type'],
        ),
        unet_seg_model_type=dict(
            widget_type='RadioButtons',
            label='Unet Model Type',
            orientation='horizontal',
            choices=unet_seg_model_type_choices,
            value=DEFAULTS_MODEL['unet_seg_model_type'],
        ),
        den_model_type=dict(
            widget_type='RadioButtons',
            label='Denoising Model Type',
            orientation='horizontal',
            choices=den_model_type_choices,
            value=DEFAULTS_MODEL['den_model_type'],
        ),
        model2d_star=dict(
            widget_type='ComboBox',
            visible=False,
            label='Pre-trained StarDist Model',
            choices=models2d_star,
            value=DEFAULTS_MODEL['model2d_star'],
        ),
        model3d_star=dict(
            widget_type='ComboBox',
            visible=False,
            label='Pre-trained StarDist Model',
            choices=models3d_star,
            value=DEFAULTS_MODEL['model3d_star'],
        ),
        model_unet=dict(
            widget_type='ComboBox',
            visible=False,
            label='Pre-trained UNET Model',
            choices=models_unet,
            value=DEFAULTS_MODEL['model_unet'],
        ),
        model_den=dict(
            widget_type='ComboBox',
            visible=False,
            label='Pre-trained CARE Denoising Model',
            choices=models_den,
            value=DEFAULTS_MODEL['model_den'],
        ),
        model_den_none=dict(widget_type='Label', visible=False, label='No Denoising'),
        model_unet_none=dict(widget_type='Label', visible=False, label='NOUNET'),
        model_star_none=dict(widget_type='Label', visible=False, label='NOSTAR'),
        model_folder_star=dict(
            widget_type='FileEdit',
            visible=False,
            label='Custom StarDist Model',
            mode='d',
        ),
        model_folder_unet=dict(
            widget_type='FileEdit', visible=False, label='Custom UNET Model', mode='d'
        ),
        model_folder_den=dict(
            widget_type='FileEdit',
            visible=False,
            label='Custom Denoising Model',
            mode='d',
        ),
        model_axes=dict(widget_type='LineEdit', label='Model Axes', value=''),
        norm_axes=dict(
            widget_type='LineEdit',
            label='Normalization Axes',
            value=DEFAULTS_MODEL['norm_axes'],
        ),
        defaults_model_button=dict(
            widget_type='PushButton', text='Restore Model Defaults'
        ),
        progress_bar=dict(label=' ', min=0, max=0, visible=False),
        layout='vertical',
        persist=True,
        call_button=True,
    )
    @thread_worker
    def plugin(
        viewer: napari.Viewer,
        label_head,
        image: napari.layers.Image,
        axes,
        star_seg_model_type,
        unet_seg_model_type,
        den_model_type,
        model2d_star,
        model3d_star,
        model_unet,
        model_den,
        model_den_none,
        model_unet_none,
        model_star_none,
        model_folder_star,
        model_folder_unet,
        model_folder_den,
        model_axes,
        norm_axes,
        defaults_model_button,
        progress_bar: mw.ProgressBar,
    ) -> List[napari.types.LayerDataTuple]:
        x = get_data(image)
        axes = axes_check_and_normalize(axes, length=x.ndim)
        progress_bar.label = 'Starting VollSeg'
        if plugin_star_parameters.norm_image:
            axes_norm = axes_check_and_normalize(norm_axes)
            axes_norm = ''.join(
                set(axes_norm).intersection(set(axes))
            )  # relevant axes present in input image
            assert len(axes_norm) > 0
            # always jointly normalize channels for RGB images
            if ('C' in axes and image.rgb == True) and ('C' not in axes_norm):
                axes_norm = axes_norm + 'C'
                
                warn('jointly normalizing channels of RGB input image')
            ax = axes_dict(axes)
            
            _axis = tuple(sorted(ax[a] for a in axes_norm))
            # # TODO: address joint vs. channel/time-separate normalization properly (let user choose)
            # #       also needs to be documented somewhere
            # if 'T' in axes:
            #     if 'C' not in axes or image.rgb == True:
            #          # normalize channels jointly, frames independently
            #          _axis = tuple(i for i in range(x.ndim) if i not in (ax['T'],))
            #     else:
            #         # normalize channels independently, frames independently
            #         _axis = tuple(i for i in range(x.ndim) if i not in (ax['T'],ax['C']))
            # else:
            #     if 'C' not in axes or image.rgb == True:
            #          # normalize channels jointly
            #         _axis = None
            #     else:
            #         # normalize channels independently
            #         _axis = tuple(i for i in range(x.ndim) if i not in (ax['C'],))
            x = normalize(
                x,
                plugin_star_parameters.perc_low.value,
                plugin_star_parameters.perc_high.value,
                axis=_axis,
            )
        #if model_selected_star is None and model_selected_unet is None and model_selected_den is None:
            #plugin.call_button.enabled = False
        if model_selected_star is not None:    
             model_star = get_model_star(*model_selected_star)
        else:
            model_star = None
        if model_selected_unet is not None:
            model_unet = get_model_unet(*model_selected_unet)
        else:
            model_unet = None
        if model_selected_den is not None:
            model_den = get_model_den(*model_selected_den)
        else:
            model_den = None
        lkwargs = {}
        print('selected model', model_star, model_unet, model_den)
        
        if model_star is not None:
                if not axes.replace('T', '').startswith(model_star._axes_out.replace('C', '')):
                    warn(
                        f'output images have different axes ({model_star._axes_out.replace("C","")}) than input image ({axes})'
                    )
                    
        if model_unet is not None:
                if not axes.replace('T', '').startswith(model_unet._axes_out.replace('C', '')):
                    warn(
                        f'output images have different axes ({model_unet._axes_out.replace("C","")}) than input image ({axes})'
                    )            
            # TODO: adjust image.scale according to shuffled axes
        # don't want to load persisted values for these widgets

        # TODO: progress bar (labels) often don't show up. events not processed?
        if 'T' in axes:
            app = use_app()
            t = axes_dict(axes)['T']
            n_frames = x.shape[t]
            if plugin_star_parameters.n_tiles.value is not None:
                # remove tiling value for time axis
                plugin_star_parameters.n_tiles.value = tuple(
                    v
                    for i, v in enumerate(plugin_star_parameters.n_tiles.value)
                    if i != t
                )

            def progress(it, **kwargs):
                progress_bar.label = 'VollSeg Prediction (frames)'
                progress_bar.range = (0, n_frames)
                progress_bar.value = 0
                progress_bar.show()
                app.process_events()
                for item in it:
                    yield item
                    plugin.progress_bar.increment()
                    app.process_events()
                app.process_events()

        elif plugin_star_parameters.n_tiles.value is not None and np.prod(plugin_star_parameters.n_tiles.value) > 1:
            plugin_star_parameters.n_tiles.value = tuple(plugin_star_parameters.n_tiles.value)
            app = use_app()

            def progress(it, **kwargs):
                progress_bar.label = 'CNN Prediction (tiles)'
                progress_bar.range = (0, kwargs.get('total', 0))
                progress_bar.value = 0
                progress_bar.show()
                app.process_events()
                for item in it:
                    yield item
                    progress_bar.increment()
                    app.process_events()
                #
                progress_bar.label = 'NMS Postprocessing'
                progress_bar.range = (0, 0)
                app.process_events()

        else:
            progress = False
            progress_bar.label = 'VollSeg Prediction'
            progress_bar.range = (0, 0)
            progress_bar.show()
            use_app().process_events()
        if model_star is not None:
                # semantic output axes of predictions
                assert model_star._axes_out[-1] == 'C'
                axes_out = list(model_star._axes_out[:-1])
        if model_unet is not None:
                # semantic output axes of predictions
                assert model_unet._axes_out[-1] == 'C'
                axes_out = list(model_unet._axes_out[:-1])        
        if 'T' in axes:
            x_reorder = np.moveaxis(x, t, 0)
            
            axes_reorder = axes.replace('T', '')
            axes_out.insert(t, 'T')
            
            if model_den is not None:
                noise_model = plugin.model_den

            if model_den == None:
                noise_model = None
                
            if isinstance(model_star, StarDist3D):

                if plugin_star_parameters.n_tiles.value is None:
                    
                    plugin_star_parameters.n_tiles.value = (1,1,1)
                pred = tuple(
                    zip(
                        *tuple(
                            VollSeg3D(
                                _x,
                                model_unet,
                                model_star,
                                axes=axes_reorder,
                                noise_model=noise_model,
                                prob_thresh=plugin_star_parameters.prob_thresh.value,
                                nms_thresh=plugin_star_parameters.nms_thresh.value,
                                min_size_mask=plugin_extra_parameters.min_size_mask.value,
                                min_size=plugin_extra_parameters.min_size.value,
                                max_size=plugin_extra_parameters.max_size.value,
                                n_tiles=plugin_star_parameters.n_tiles.value,
                                UseProbability=plugin_extra_parameters.prob_map_watershed.Value,
                                dounet=plugin_extra_parameters.dounet.value,
                                slice_merge = plugin_extra_parameters.slicemerge.value,
                                iou_threshold = plugin_extra_parameters.iouthresh.value
                            )
                            for _x in progress(x_reorder)
                        )
                    )
                )
                
            

            if isinstance(model_star, StarDist2D):

                

                print('Starting VollSeg')
                if plugin_star_parameters.n_tiles.value is None:
                    
                    plugin_star_parameters.n_tiles.value = (1,1)
                pred = tuple(
                    zip(
                        *tuple(
                            VollSeg2D(
                                _x,
                                model_unet,
                                model_star,
                                axes=axes_reorder,
                                noise_model=noise_model,
                                prob_thresh=plugin_star_parameters.prob_thresh.value,
                                nms_thresh=plugin_star_parameters.nms_thresh.value,
                                min_size_mask=plugin_extra_parameters.min_size_mask.value,
                                min_size=plugin_extra_parameters.min_size.value,
                                max_size=plugin_extra_parameters.max_size.value,
                                n_tiles=plugin_star_parameters.n_tiles.value,
                                UseProbability=plugin_extra_parameters.prob_map_watershed.value,
                                dounet=plugin_extra_parameters.dounet.value,
                                RGB = plugin_extra_parameters.isRGB.value,
                            )
                            for _x in progress(x_reorder)
                        )
                    )
                )
                
                
            if model_star is None and model_unet is not None:
                    if plugin_star_parameters.n_tiles.value is None:
                        
                        plugin_star_parameters.n_tiles.value = (1,1)
                        
                    pred = [VollSeg_unet(_x, model_unet, n_tiles=plugin_star_parameters.n_tiles.value, axes = axes_reorder, noise_model = noise_model,  RGB = plugin_extra_parameters.isRGB.value,
                                         iou_threshold = plugin_extra_parameters.iouthresh.value,slice_merge = plugin_extra_parameters.slicemerge.value)for _x in progress(x_reorder)]
                        


            if noise_model is not None:

                labels, unet_mask, star_labels, probability_map, Markers, denoised_image = pred
                
                denoised_image = np.asarray(denoised_image)
    
                denoised_image = np.moveaxis(denoised_image, 0, t)
                
                denoised_image = np.reshape(denoised_image, x.shape)
                
                
            elif model_star is not None:
                
                labels, unet_mask, star_labels, probability_map, Markers = pred
                
                
            elif model_star is None and model_unet is not None:
                   unet_mask = pred
                   
                   unet_mask = np.asarray(unet_mask)
                   unet_mask = unet_mask > 0
                   unet_mask = np.moveaxis(unet_mask, 0, t)
                   unet_mask = np.reshape(unet_mask, x.shape)
            if model_star is not None: 
                    labels = np.asarray(labels)
        
                    labels = np.moveaxis(labels, 0, t)
                    
                    labels = np.reshape(labels, x.shape)
                    
                    star_labels = np.asarray(star_labels)
        
                    star_labels = np.moveaxis(star_labels, 0, t)
                    
                    star_labels = np.reshape(star_labels, x.shape)
                    probability_map = np.asarray(probability_map)
        
                    probability_map = np.moveaxis(probability_map, 0, t)
                    probability_map = np.reshape(probability_map, x.shape)
                    Markers = np.asarray(Markers)
        
                    Markers = np.moveaxis(Markers, 0, t)
                    Markers = np.reshape(Markers, x.shape)
        else:
            
            if model_den is not None:
                noise_model = plugin.model_den

            if model_den == None:
                noise_model = None
            # TODO: possible to run this in a way that it can be canceled?
            if isinstance(model_star, StarDist3D):

                if plugin_star_parameters.n_tiles.value is None:
                    
                    plugin_star_parameters.n_tiles.value = (1,1,1)
                if model_star is not None: 
                    
                    
                       worker = _Segment3D(model_star, model_unet, x, axes, noise_model)
                       worker.returned.connect(return_segment)
                       worker.start()
                       
            
            if isinstance(model_star, StarDist2D):

                
                print('Starting VollSeg')
                if plugin_star_parameters.n_tiles.value is None:
                    
                    plugin_star_parameters.n_tiles.value = (1,1)
                if model_star is not None:
                        pred = VollSeg2D(
                            x,
                            model_unet,
                            model_star,
                            axes=axes,
                            noise_model=noise_model,
                            prob_thresh=plugin_star_parameters.prob_thresh.value,
                            nms_thresh=plugin_star_parameters.nms_thresh.value,
                            min_size_mask=plugin_extra_parameters.min_size_mask.value,
                            min_size=plugin_extra_parameters.min_size.value,
                            max_size=plugin_extra_parameters.max_size.value,
                            n_tiles=plugin_star_parameters.n_tiles.value,
                            UseProbability=plugin_extra_parameters.prob_map_watershed.value,
                            dounet=plugin_extra_parameters.dounet.value,
                            RGB = plugin_extra_parameters.isRGB.value,
                        )
            if model_star is None and model_unet is not None:
                if plugin_star_parameters.n_tiles.value is None:
                    
                    plugin_star_parameters.n_tiles.value = 1
                    for i in range(len(x.shape)):
                         plugin_star_parameters.n_tiles.value = plugin_star_parameters.n_tiles.value + (1,)
                         
                worker = _Unet3D(model_unet, x, axes, noise_model)
                worker.returned.connect(return_segment)
                worker.start()         
                
            if model_den is not None:

                labels, unet_mask, star_labels, probability_map, Markers, Skeleton, denoised_image = pred
            elif model_den is None and model_star is not None:
                labels, unet_mask, star_labels, probability_map, Markers, Skeleton = pred
                
            if model_star is None:
                
                if model_den is None:
                    
                     unet_mask = pred
                else:
                    
                    denoised_image, unet_mask = pred

        progress_bar.hide()
        # determine scale for output axes
        scale_in_dict = dict(zip(axes, image.scale))
        scale_out = [scale_in_dict.get(a, 1.0) for a in axes_out]
            
        layers = []

        
            
        if model_star is not None:
            layers.append(
                (
                    probability_map,
                    dict(
                        name='Base Watershed Image',
                        scale=scale_out,
                        visible=False,
                        **lkwargs,
                    ),
                    'image',
                )
            )

            layers.append(
                (
                    labels,
                    dict(
                        name='VollSeg labels', scale=scale_out, opacity=0.5, **lkwargs,
                    ),
                    'labels',
                )
            )

            layers.append(
                (
                    star_labels,
                    dict(
                        name='StarDist',
                        scale=scale_out,
                        opacity=0.5,
                        visible=False,
                        **lkwargs,
                    ),
                    'labels',
                )
            )
            layers.append(
                (
                    unet_mask,
                    dict(
                        name='VollSeg Binary',
                        scale=scale_out,
                        opacity=0.5,
                        visible=False,
                        **lkwargs,
                    ),
                    'labels',
                )
            )

            layers.append(
                (
                    Markers,
                    dict(
                        name='Markers',
                        scale=scale_out,
                        opacity=0.5,
                        visible=False,
                        **lkwargs,
                    ),
                    'labels',
                )
            )
            layers.append(
                (
                    Skeleton,
                    dict(
                        name='Skeleton',
                        scale=scale_out,
                        opacity=0.5,
                        visible=False,
                        **lkwargs,
                    ),
                    'labels',
                )
            )
        if noise_model is not None:
            layers.append(
                (
                    denoised_image,
                    dict(
                        name='Denoised Image',
                        scale=scale_out,
                        visible=False,
                        **lkwargs,
                    ),
                    'image',
                )
            )

        if model_unet is not None:
            layers.append(
                (
                    unet_mask,
                    dict(
                        name='VollSeg Binary',
                        scale=scale_out,
                        opacity=0.5,
                        visible=False,
                        **lkwargs,
                    ),
                    'labels',
                )
            )

        return layers

    plugin.axes.value = ''
    plugin_star_parameters.n_tiles.value = DEFAULTS_STAR_PARAMETERS['n_tiles']
    plugin.label_head.value = '<small>VollSeg segmentation for 2D and 3D images.<br>If you are using this in your research please <a href="https://github.com/kapoorlab/vollseg#how-to-cite" style="color:gray;">cite us</a>.</small><br><br><tt><a href="http://conference.scipy.org/proceedings/scipy2021/varun_kapoor.html" style="color:gray;">VollSeg Scipy</a></tt>'
    plugin.label_head.native.setSizePolicy(
        QSizePolicy.MinimumExpanding, QSizePolicy.Fixed
    )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    #
    widget_for_modeltype = {
        StarDist2D: plugin.model2d_star,
        StarDist3D: plugin.model3d_star,
        UNET: plugin.model_unet,
        CARE: plugin.model_den,
        'NODEN': plugin.model_den_none,
        'NOUNET': plugin.model_unet_none,
        'NOSTAR': plugin.model_star_none,
        CUSTOM_SEG_MODEL_STAR: plugin.model_folder_star,
        CUSTOM_SEG_MODEL_UNET: plugin.model_folder_unet,
        CUSTOM_DEN_MODEL: plugin.model_folder_den,
    }

    tabs = QTabWidget()

    parameter_star_tab = QWidget()
    _parameter_star_tab_layout = QVBoxLayout()
    parameter_star_tab.setLayout(_parameter_star_tab_layout)
    _parameter_star_tab_layout.addWidget(plugin_star_parameters.native)
    tabs.addTab(parameter_star_tab, 'StarDist Parameter Selection')

    parameter_extra_tab = QWidget()
    _parameter_extra_tab_layout = QVBoxLayout()
    parameter_extra_tab.setLayout(_parameter_extra_tab_layout)
    _parameter_extra_tab_layout.addWidget(plugin_extra_parameters.native)
    tabs.addTab(parameter_extra_tab, 'VollSeg Parameter Selection')
    plugin.native.layout().addWidget(tabs)

    def widgets_inactive(*widgets, active):
        for widget in widgets:
            widget.visible = active
            # widget.native.setStyleSheet('' if active else 'text-decoration: line-through')

    def widgets_valid(*widgets, valid):
        for widget in widgets:
            widget.native.setStyleSheet('' if valid else 'background-color: lightcoral')

    class Unet_den_updater:
        def __init__(self, debug=DEBUG):
            from types import SimpleNamespace

            self.debug = debug
            self.valid = SimpleNamespace(
                **{
                    k: False
                    for k in ('image_axes', 'model_den', 'n_tiles', 'norm_axes')
                }
            )
            self.args = SimpleNamespace()
            self.viewer = None

        def __call__(self, k, valid, args=None):
            assert k in vars(self.valid)
            setattr(self.valid, k, bool(valid))
            setattr(self.args, k, args)
            self._update()

        def help(self, msg):
            if self.viewer is not None:
                self.viewer.help = msg
            elif len(str(msg)) > 0:
                print(f'HELP: {msg}')

        def _update(self):

            # try to get a hold of the viewer (can be None when plugin starts)
            if self.viewer is None:
                # TODO: when is this not safe to do and will hang forever?
                # while plugin.viewer.value is None:
                #     time.sleep(0.01)
                if plugin.viewer.value is not None:
                    self.viewer = plugin.viewer.value
                    if DEBUG:
                        print('GOT viewer')

                    @self.viewer.layers.events.removed.connect
                    def _layer_removed(event):
                        layers_remaining = event.source
                        if len(layers_remaining) == 0:
                            plugin.image.tooltip = ''
                            plugin.axes.value = ''
                            plugin_star_parameters.n_tiles.value = 'None'

            def _model(valid):
                widgets_valid(
                    plugin.model_den, plugin.model_folder_den.line_edit, valid=valid,
                )
                if valid:
                    print(valid)
                    config_den = self.args.model_unet
                    axes_den = config_den.get('axes')
                    if 'T' in axes_den:
                        raise RuntimeError('model with axis "T" not supported')
                    plugin.model_axes.value = axes_den.replace('C', f'C[{config_den["n_channel_in"]}]')     
                    plugin.model_folder_den.line_edit.tooltip = ''

                    return axes_den, config_den
                else:
                    plugin.model_folder_den.line_edit.tooltip = (
                        'Invalid model directory'
                    )

            def _image_axes(valid):
                axes, image, err = getattr(self.args, 'image_axes', (None, None, None))
                widgets_valid(
                    plugin.axes,
                    valid=(
                        valid or (image is None and (axes is None or len(axes) == 0))
                    ),
                )
                

                if valid:
                    plugin.axes.tooltip = '\n'.join(
                        [f'{a} = {s}' for a, s in zip(axes, get_data(image).shape)]
                    )
                    return axes, image
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.axes.tooltip = ''

            def _norm_axes(valid):
                norm_axes, err = getattr(self.args, 'norm_axes', (None, None))
                widgets_valid(plugin.norm_axes, valid=valid)
                if valid:
                    plugin.norm_axes.tooltip = f'Axes to jointly normalize (if present in selected input image). Note: channels of RGB images are always normalized together.'
                    return norm_axes
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.norm_axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.norm_axes.tooltip = ''

            def _n_tiles(valid):
                n_tiles, image, err = getattr(self.args, 'n_tiles', (None, None, None))
                widgets_valid(
                    plugin_star_parameters.n_tiles, valid=(valid or image is None)
                )
                if valid:
                    plugin_star_parameters.n_tiles.tooltip = (
                        'no tiling'
                        if n_tiles is None
                        else '\n'.join(
                            [
                                f'{t}: {s}'
                                for t, s in zip(n_tiles, get_data(image).shape)
                            ]
                        )
                    )
                    return n_tiles
                else:
                    msg = str(err) if err is not None else ''
                    plugin_star_parameters.n_tiles.tooltip = msg

            def _no_tiling_for_axis(axes_image, n_tiles, axis):
                if n_tiles is not None and axis in axes_image:
                    return n_tiles[axes_dict(axes_image)[axis]] == 1
                return True

            def _restore():
                widgets_valid(plugin.image, valid=plugin.image.value is not None)

            all_valid = False
            help_msg = ''

            if (
                self.valid.image_axes
                and self.valid.n_tiles
                and self.valid.model_den
                and self.valid.norm_axes
            ):
                axes_image, image = _image_axes(True)
                (axes_model_den, config_den) = _model(True)
                axes_norm = _norm_axes(True)
                n_tiles = _n_tiles(True)
                if not _no_tiling_for_axis(axes_image, n_tiles, 'C'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for C axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                elif not _no_tiling_for_axis(axes_image, n_tiles, 'T'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for T axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                elif set(axes_norm).isdisjoint(set(axes_image)):
                    # check if image axes and normalization axes are compatible
                    widgets_valid(plugin.norm_axes, valid=False)
                    err = f'Image axes ({axes_image}) must contain at least one of the normalization axes ({", ".join(axes_norm)})'
                    plugin.norm_axes.tooltip = err
                    _restore()
                elif (
                    'T' in axes_image
                    and config_den.get('n_dim') == 3
                    
                ):
                    # not supported
                    
                    _restore()
                else:
                    # check if image and models are compatible
                    ch_model_den = config_den['n_channel_in']
                    ch_image = (
                        get_data(image).shape[axes_dict(axes_image)['C']]
                        if 'C' in axes_image
                        else 1
                    )
                    all_valid = (
                        set(axes_model_den.replace('C', ''))
                        == set(axes_image.replace('C', '').replace('T', ''))
                        and ch_model_den == ch_image
                    )

                    widgets_valid(
                        plugin.image,
                        plugin.model_den,
                        plugin.model_folder_den.line_edit,
                        valid=all_valid,
                    )
                    if all_valid:
                        help_msg = ''
                    else:
                        help_msg = f'Model with axes {axes_model_den.replace("C", f"C[{ch_model_den}]")} and image with axes {axes_image.replace("C", f"C[{ch_image}]")} not compatible'
            else:
                _image_axes(self.valid.image_axes)
                _norm_axes(self.valid.norm_axes)
                _n_tiles(self.valid.n_tiles)
                _model(self.valid.model_den)

                _restore()

            self.help(help_msg)
            if all_valid:
                plugin.call_button.enabled = True
            # widgets_valid(plugin.call_button, valid=all_valid)
            if self.debug:
                print(
                    f'valid ({all_valid}):',
                    ', '.join([f'{k}={v}' for k, v in vars(self.valid).items()]),
                )

    class Unet_updater:
        def __init__(self, debug=DEBUG):
            from types import SimpleNamespace

            self.debug = debug
            self.valid = SimpleNamespace(
                **{
                    k: False
                    for k in ('image_axes', 'model_unet', 'n_tiles', 'norm_axes')
                }
            )
            self.args = SimpleNamespace()
            self.viewer = None

        def __call__(self, k, valid, args=None):
            assert k in vars(self.valid)
            setattr(self.valid, k, bool(valid))
            setattr(self.args, k, args)
            print('unet again',self.valid, self.args)
            self._update()

        def help(self, msg):
            if self.viewer is not None:
                self.viewer.help = msg
            elif len(str(msg)) > 0:
                print(f'HELP: {msg}')
        
        def _update(self):

            print('what is unet',plugin.model_unet)
            # try to get a hold of the viewer (can be None when plugin starts)
            if self.viewer is None:
                # TODO: when is this not safe to do and will hang forever?
                # while plugin.viewer.value is None:
                #     time.sleep(0.01)
                if plugin.viewer.value is not None:
                    self.viewer = plugin.viewer.value
                    if DEBUG:
                        print('GOT viewer')

                    @self.viewer.layers.events.removed.connect
                    def _layer_removed(event):
                        layers_remaining = event.source
                        if len(layers_remaining) == 0:
                            plugin.image.tooltip = ''
                            plugin.axes.value = ''
                            plugin_star_parameters.n_tiles.value = 'None'

            def _model(valid):
                widgets_valid(
                    plugin.model_unet, plugin.model_folder_unet.line_edit, valid=valid,
                )
                print('unet',plugin.model_unet, plugin.model_folder_unet.line_edit, valid)
                if valid:
                    print(valid)
                    config_unet = self.args.model_unet
                    axes_unet = config_unet.get(
                        'axes', 'ZYXC'[-len(config_unet['unet_input_shape']) :]
                    )
                    print('unet axes',axes_unet)
                    if 'T' in axes_unet:
                        raise RuntimeError('model with axis "T" not supported')
                    plugin.model_axes.value = axes_unet.replace('C', f'C[{config_unet["n_channel_in"]}]')    
                    plugin.model_folder_unet.line_edit.tooltip = ''
                    return axes_unet, config_unet
                else:
                    plugin.model_folder_unet.line_edit.tooltip = (
                        'Invalid model directory'
                    )

            def _image_axes(valid):
                axes, image, err = getattr(self.args, 'image_axes', (None, None, None))
                
                print('image axes',axes)
                widgets_valid(
                    plugin.axes,
                    valid=(
                        valid or (image is None and (axes is None or len(axes) == 0))
                    ),
                )
                

                if valid:
                    plugin.axes.tooltip = '\n'.join(
                        [f'{a} = {s}' for a, s in zip(axes, get_data(image).shape)]
                    )
                    return axes, image
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.axes.tooltip = ''

            def _norm_axes(valid):
                norm_axes, err = getattr(self.args, 'norm_axes', (None, None))
                widgets_valid(plugin.norm_axes, valid=valid)
                if valid:
                    plugin.norm_axes.tooltip = f'Axes to jointly normalize (if present in selected input image). Note: channels of RGB images are always normalized together.'
                    return norm_axes
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.norm_axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.norm_axes.tooltip = ''

            def _n_tiles(valid):
                n_tiles, image, err = getattr(self.args, 'n_tiles', (None, None, None))
                widgets_valid(
                    plugin_star_parameters.n_tiles, valid=(valid or image is None)
                )
                if valid:
                    plugin_star_parameters.n_tiles.tooltip = (
                        'no tiling'
                        if n_tiles is None
                        else '\n'.join(
                            [
                                f'{t}: {s}'
                                for t, s in zip(n_tiles, get_data(image).shape)
                            ]
                        )
                    )
                    return n_tiles
                else:
                    msg = str(err) if err is not None else ''
                    plugin_star_parameters.n_tiles.tooltip = msg

            def _no_tiling_for_axis(axes_image, n_tiles, axis):
                if n_tiles is not None and axis in axes_image:
                    return n_tiles[axes_dict(axes_image)[axis]] == 1
                return True

            def _restore():
                widgets_valid(plugin.image, valid=plugin.image.value is not None)

            all_valid = False
            help_msg = ''

            print('unet',self.valid.image_axes
            ,self.valid.n_tiles
            , self.valid.model_unet
            ) 
            if (
                self.valid.image_axes
                and self.valid.n_tiles
                and self.valid.model_unet
            ):
                axes_image, image = _image_axes(True)
                (axes_model_unet, config_unet) = _model(True)
                n_tiles = _n_tiles(True)
                if not _no_tiling_for_axis(axes_image, n_tiles, 'C'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for C axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                elif not _no_tiling_for_axis(axes_image, n_tiles, 'T'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for T axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                
                elif (
                    'T' in axes_image
                    and config_unet.get('n_dim') == 3
                    
                ):
                    # not supported
                    
                    _restore()
                else:
                    # check if image and models are compatible
                    ch_model_unet = config_unet['n_channel_in']
                    
                    ch_image = (
                        get_data(image).shape[axes_dict(axes_image)['C']]
                        if 'C' in axes_image
                        else 1
                    )
                    print('Channels',ch_model_unet, ch_image)
                    all_valid = (
                        set(axes_model_unet.replace('C', ''))
                        == set(axes_image.replace('C', '').replace('T', ''))
                        and ch_model_unet == ch_image
                    )

                    widgets_valid(
                        plugin.image,
                        plugin.model_unet,
                        plugin.model_folder_unet.line_edit,
                        valid=all_valid,
                    )
                    if all_valid:
                        help_msg = ''
                    else:
                        help_msg = f'Model with axes {axes_model_unet.replace("C", f"C[{ch_model_unet}]")} and image with axes {axes_image.replace("C", f"C[{ch_image}]")} not compatible'
            else:
                
                print('Invalid unet',self.valid.model_unet)
                _image_axes(self.valid.image_axes)
                _norm_axes(self.valid.norm_axes)
                _n_tiles(self.valid.n_tiles)
                _model(self.valid.model_unet)

                _restore()

            self.help(help_msg)
            if all_valid:
               plugin.call_button.enabled = True
            # widgets_valid(plugin.call_button, valid=all_valid)
            if self.debug:
                print(
                    f'valid ({all_valid}):',
                    ', '.join([f'{k}={v}' for k, v in vars(self.valid).items()]),
                )
    update_unet = Unet_updater()
    update_den = Unet_den_updater()

    class Updater:
        def __init__(self, debug=DEBUG):
            from types import SimpleNamespace

            self.debug = debug
            self.valid = SimpleNamespace(
                **{
                    k: False
                    for k in ('image_axes', 'model_star', 'n_tiles', 'norm_axes')
                }
            )
            self.args = SimpleNamespace()
            self.viewer = None

        def __call__(self, k, valid, args=None):
            assert k in vars(self.valid)
            setattr(self.valid, k, bool(valid))
            setattr(self.args, k, args)
            print('star again',self.valid, self.args)
            self._update()

        def help(self, msg):
            if self.viewer is not None:
                self.viewer.help = msg
            elif len(str(msg)) > 0:
                print(f'HELP: {msg}')

        def _update(self):
            # try to get a hold of the viewer (can be None when plugin starts)
            if self.viewer is None:
                # TODO: when is this not safe to do and will hang forever?
                # while plugin.viewer.value is None:
                #     time.sleep(0.01)
                if plugin.viewer.value is not None:
                    self.viewer = plugin.viewer.value
                    if DEBUG:
                        print('GOT viewer')

                    @self.viewer.layers.events.removed.connect
                    def _layer_removed(event):
                        layers_remaining = event.source
                        if len(layers_remaining) == 0:
                            plugin.image.tooltip = ''
                            plugin.axes.value = ''
                            plugin_star_parameters.n_tiles.value = 'None'

            def _model(valid):
                widgets_valid(
                    plugin.model2d_star,
                    plugin.model3d_star,
                    plugin.model_folder_star.line_edit,
                    valid=valid,
                )
                
                print('star',plugin.model2d_star,plugin.model3d_star, plugin.model_folder_star.line_edit, valid)
                if valid:
                    print(valid)
                    config_star = self.args.model_star
                    
                    axes_star = config_star.get(
                        'axes', 'ZYXC'[-len(config_star['net_input_shape']) :]
                    )
                    print('star axes',axes_star)
                    if 'T' in axes_star:
                        raise RuntimeError('model with axis "T" not supported')
                    plugin.model_axes.value = axes_star.replace(
                        'C', f'C[{config_star["n_channel_in"]}]'
                    )
                    
                    plugin.model_folder_star.line_edit.tooltip = ''

                    return axes_star, config_star
                else:
                    plugin.model_axes.value = ''
                    plugin.model_folder_star.line_edit.tooltip = (
                        'Invalid model directory'
                    )

            def _image_axes(valid):
                axes, image, err = getattr(self.args, 'image_axes', (None, None, None))
                print('image star axes',axes)
                widgets_valid(
                    plugin.axes,
                    valid=(
                        valid or (image is None and (axes is None or len(axes) == 0))
                    ),
                )
                

                if valid:
                    plugin.axes.tooltip = '\n'.join(
                        [f'{a} = {s}' for a, s in zip(axes, get_data(image).shape)]
                    )
                    return axes, image
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.axes.tooltip = ''

            def _norm_axes(valid):
                norm_axes, err = getattr(self.args, 'norm_axes', (None, None))
                widgets_valid(plugin.norm_axes, valid=valid)
                if valid:
                    plugin.norm_axes.tooltip = f'Axes to jointly normalize (if present in selected input image). Note: channels of RGB images are always normalized together.'
                    return norm_axes
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith('.') else err
                        plugin.norm_axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.norm_axes.tooltip = ''

            def _n_tiles(valid):
                n_tiles, image, err = getattr(self.args, 'n_tiles', (None, None, None))
                widgets_valid(
                    plugin_star_parameters.n_tiles, valid=(valid or image is None)
                )
                if valid:
                    plugin_star_parameters.n_tiles.tooltip = (
                        'no tiling'
                        if n_tiles is None
                        else '\n'.join(
                            [
                                f'{t}: {s}'
                                for t, s in zip(n_tiles, get_data(image).shape)
                            ]
                        )
                    )
                    return n_tiles
                else:
                    msg = str(err) if err is not None else ''
                    plugin_star_parameters.n_tiles.tooltip = msg

            def _no_tiling_for_axis(axes_image, n_tiles, axis):
                if n_tiles is not None and axis in axes_image:
                    return n_tiles[axes_dict(axes_image)[axis]] == 1
                return True

            def _restore():
                widgets_valid(plugin.image, valid=plugin.image.value is not None)

            all_valid = False
            help_msg = ''
            
            if (
                self.valid.image_axes
                and self.valid.n_tiles
                and self.valid.model_star
                and self.valid.norm_axes
            ):
                axes_image, image = _image_axes(True)
                (axes_model_star, config_star) = _model(True)
                axes_norm = _norm_axes(True)
                n_tiles = _n_tiles(True)
                if not _no_tiling_for_axis(axes_image, n_tiles, 'C'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for C axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                elif not _no_tiling_for_axis(axes_image, n_tiles, 'T'):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin_star_parameters.n_tiles, valid=False)
                    err = 'number of tiles must be 1 for T axis'
                    plugin_star_parameters.n_tiles.tooltip = err
                    _restore()
                elif set(axes_norm).isdisjoint(set(axes_image)):
                    # check if image axes and normalization axes are compatible
                    widgets_valid(plugin.norm_axes, valid=False)
                    err = f'Image axes ({axes_image}) must contain at least one of the normalization axes ({", ".join(axes_norm)})'
                    plugin.norm_axes.tooltip = err
                    _restore()
                elif (
                    'T' in axes_image
                    and config_star.get('n_dim') == 3
                    
                ):
                    # not supported
                    
                    _restore()
                else:
                    # check if image and models are compatible
                    ch_model_star = config_star['n_channel_in']
                    ch_image = (
                        get_data(image).shape[axes_dict(axes_image)['C']]
                        if 'C' in axes_image
                        else 1
                    )
                    all_valid = (
                        set(axes_model_star.replace('C', ''))
                        == set(axes_image.replace('C', '').replace('T', ''))
                        and ch_model_star == ch_image
                    )

                    widgets_valid(
                        plugin.image,
                        plugin.model2d_star,
                        plugin.model3d_star,
                        plugin.model_folder_star.line_edit,
                        valid=all_valid,
                    )
                    if all_valid:
                        help_msg = ''
                    else:
                        help_msg = f'Model with axes {axes_model_star.replace("C", f"C[{ch_model_star}]")} and image with axes {axes_image.replace("C", f"C[{ch_image}]")} not compatible'
            else:
                
                _image_axes(self.valid.image_axes)
                _norm_axes(self.valid.norm_axes)
                _n_tiles(self.valid.n_tiles)
                _model(self.valid.model_star)
 
                _restore()

            self.help(help_msg)
            if all_valid:
              plugin.call_button.enabled = True
            # widgets_valid(plugin.call_button, valid=all_valid)
            if self.debug:
                print(
                    f'valid ({all_valid}):',
                    ', '.join([f'{k}={v}' for k, v in vars(self.valid).items()]),
                )
    update = Updater()

    def select_model_star(key_star):
        nonlocal model_selected_star
        model_selected_star = key_star
        config_star = model_star_configs.get(key_star)
        update('model_star', config_star is not None, config_star)

    def select_model_unet(key_unet):
        nonlocal model_selected_unet
        model_selected_unet = key_unet
        config_unet = model_unet_configs.get(key_unet)
        update_unet('model_unet', config_unet is not None, config_unet)

    def select_model_den(key_den):
        nonlocal model_selected_den
        model_selected_den = key_den
        config_den = model_den_configs.get(key_den)
        update_den('model_den', config_den is not None, config_den)

    # -------------------------------------------------------------------------

    # hide percentile selection if normalization turned off
    @change_handler(plugin_star_parameters.norm_image)
    def _norm_image_change(active: bool):
        widgets_inactive(
            plugin_star_parameters.perc_low,
            plugin_star_parameters.perc_high,
            plugin.norm_axes,
            active=active,
        )

    @change_handler(plugin_extra_parameters.dounet)
    def _dounet_change(active: bool):
        plugin_extra_parameters.dounet.value = active
        
        
    @change_handler(plugin_extra_parameters.slicemerge)
    def _slicemerge_change(active: bool):
        plugin_extra_parameters.slicemerge.value = active
        widgets_inactive(
            plugin_extra_parameters.iouthresh,
            active=active,
        )
        
    @change_handler(plugin_extra_parameters.isRGB)
    def _dorgb_change(active: bool):
        plugin_extra_parameters.isRGB.value = active

    @change_handler(plugin_extra_parameters.prob_map_watershed)
    def _prob_map_watershed_change(active: bool):
        plugin_extra_parameters.prob_map_watershed.value = active

    # ensure that percentile low < percentile high
    @change_handler(plugin_star_parameters.perc_low)
    def _perc_low_change():
        plugin_star_parameters.perc_high.value = max(
            plugin_star_parameters.perc_low.value + 0.01,
            plugin_star_parameters.perc_high.value,
        )

    @change_handler(plugin_star_parameters.perc_high)
    def _perc_high_change():
        plugin_star_parameters.perc_low.value = min(
            plugin_star_parameters.perc_low.value,
            plugin_star_parameters.perc_high.value - 0.01,
        )

    @change_handler(plugin.norm_axes)
    def _norm_axes_change(value: str):
        if value != value.upper():
            with plugin.axes.changed.blocked():
                plugin.norm_axes.value = value.upper()
        try:
            axes = axes_check_and_normalize(value, disallowed='S')
            if len(axes) >= 1:
                update('norm_axes', True, (axes, None))
                update_unet('norm_axes', True, (axes, None))
                update_den('norm_axes', True, (axes, None))
            else:
                update('norm_axes', False, (axes, 'Cannot be empty'))
                update_unet('norm_axes', False, (axes, 'Cannot be empty'))
                update_den('norm_axes', False, (axes, 'Cannot be empty'))
        except ValueError as err:
            update('norm_axes', False, (value, err))
            update_unet('norm_axes', False, (value, err))
            update_den('norm_axes', False, (value, err))
    # -------------------------------------------------------------------------

    # RadioButtons widget triggers a change event initially (either when 'value' is set in constructor, or via 'persist')
    # TODO: seems to be triggered too when a layer is added or removed (why?)
    @change_handler(plugin.star_seg_model_type, init=False)
    def _seg_model_type_change_star(seg_model_type: Union[str, type]):
        selected = widget_for_modeltype[seg_model_type]
        for w in set(
            (
                plugin.model2d_star,
                plugin.model3d_star,
                plugin.model_star_none,
                plugin.model_folder_star,
            )
        ) - {selected}:
            w.hide()
        selected.show()
        # trigger _model_change_star()
        selected.changed(selected.value)

    @change_handler(plugin.unet_seg_model_type, init=False)
    def _seg_model_type_change_unet(seg_model_type: Union[str, type]):
        selected = widget_for_modeltype[seg_model_type]
        for w in set(
            (plugin.model_unet, plugin.model_unet_none, plugin.model_folder_unet)
        ) - {selected}:
            w.hide()
        selected.show()
        # trigger _model_change_unet
        selected.changed(selected.value)

    # RadioButtons widget triggers a change event initially (either when 'value' is set in constructor, or via 'persist')
    # TODO: seems to be triggered too when a layer is added or removed (why?)
    @change_handler(plugin.den_model_type, init=False)
    def _den_model_type_change(den_model_type: Union[str, type]):
        selected = widget_for_modeltype[den_model_type]
        for w in set(
            (plugin.model_den, plugin.model_den_none, plugin.model_folder_den)
        ) - {selected}:
            w.hide()
        selected.show()

        # trigger _model_change_den
        selected.changed(selected.value)

    # show/hide model folder picker
    # load config/thresholds for selected pretrained model
    # -> triggered by _model_type_change
    @change_handler(plugin.model2d_star, plugin.model3d_star,plugin.model_star_none, init=False)
    def _model_change_star(model_name_star: str):

        print(plugin.model2d_star, plugin.model3d_star)
        model_class_star = (
            StarDist2D if Signal.sender() is plugin.model2d_star else StarDist3D if Signal.sender() is plugin.model3d_star else None
        )
        
        if model_class_star is not None:
                key_star = model_class_star, model_name_star
                if key_star not in model_star_configs:
                    print('key stars',key_star, model_star_configs)
                    @thread_worker
                    def _get_model_folder():
                        return get_model_folder(*key_star)
        
                    def _process_model_folder(path):
                        try:
                            model_star_configs[key_star] = load_json(str(path / 'config.json'))
                            try:
                                # not all models have associated thresholds
                                model_star_threshs[key_star] = load_json(
                                    str(path / 'thresholds.json')
                                )
                            except FileNotFoundError:
                                pass
                        finally:
                            select_model_star(key_star)
                            plugin.progress_bar.hide()
        
                    worker = _get_model_folder()
                    worker.returned.connect(_process_model_folder)
                    worker.start()
        
                    # delay showing progress bar -> won't show up if model already downloaded
                    # TODO: hacky -> better way to do this?
                    time.sleep(0.1)
                    plugin.call_button.enabled = False
                    plugin.progress_bar.label = 'Downloading StarDist model'
                    plugin.progress_bar.show()

                else:
                    select_model_star(key_star)
        else:
             plugin.call_button.enabled = False
             key_star = None, None
             select_model_star(key_star)
             
    @thread_worker         
    def _Unet3D( model_unet, x, axes, noise_model):
    
        print('INside')
        pred = VollSeg_unet(x, model_unet, n_tiles=plugin_star_parameters.n_tiles.value, axes = axes, noise_model = noise_model, RGB = plugin_extra_parameters.isRGB.value,
                            iou_threshold = plugin_extra_parameters.iouthresh.value,slice_merge = plugin_extra_parameters.slicemerge.value)

   
        print('UNET pred', pred)                 
        return pred            
             
    @thread_worker         
    def _Segment3D(model_star, model_unet, x, axes, noise_model):
    
        
        pred = VollSeg3D(
            x,
            model_unet,
            model_star,
            axes=axes,
            noise_model=noise_model,
            prob_thresh=plugin_star_parameters.prob_thresh.value,
            nms_thresh=plugin_star_parameters.nms_thresh.value,
            min_size_mask=plugin_extra_parameters.min_size_mask.value,
            min_size=plugin_extra_parameters.min_size.value,
            max_size=plugin_extra_parameters.max_size.value,
            n_tiles=plugin_star_parameters.n_tiles.value,
            UseProbability=plugin_extra_parameters.prob_map_watershed.value,
            dounet=plugin_extra_parameters.dounet.value,
            slice_merge = plugin_extra_parameters.slicemerge.value,
            iou_threshold = plugin_extra_parameters.iouthresh.value
            )   
                         
        return pred  

    def return_segment(pred):
        
          print('Prediction',pred)
          

                                 
             
    @change_handler(plugin.model_unet, plugin.model_unet_none, init=False) 
    def _model_change_unet(model_name_unet: str):
        model_class_unet = ( UNET if Signal.sender() is plugin.model_unet else None ) 
        print('class unet',model_class_unet)
        if model_class_unet is not None:
                key_unet = model_class_unet, model_name_unet
                print('key unets',key_unet, model_unet_configs)
                if key_unet not in model_unet_configs:
        
                    @thread_worker
                    def _get_model_folder():
                        return get_model_folder(*key_unet)
        
                    def _process_model_folder(path):
        
                        try:
                            model_unet_configs[key_unet] = load_json(str(path / 'config.json'))
                            
                        finally:
        
                                select_model_unet(key_unet)
                                plugin.progress_bar.hide()
        
                    worker = _get_model_folder()
                    worker.returned.connect(_process_model_folder)
                    worker.start()
        
                    # delay showing progress bar -> won't show up if model already downloaded
                    # TODO: hacky -> better way to do this?
                    time.sleep(0.1)
                    plugin.call_button.enabled = False
                    plugin.progress_bar.label = 'Downloading UNET model'
                    plugin.progress_bar.show()
        
                else:
                    select_model_unet(key_unet)
        else:
                 plugin.call_button.enabled = False
                 key_unet = None, None 
                 select_model_unet(key_unet)
    @change_handler(plugin.model_den, init=False)
    def _model_change_den(model_name_den: str):
        model_class_den = CARE

        key_den = model_class_den, model_name_den
        if key_den not in model_den_configs:

            @thread_worker
            def _get_model_folder():
                return get_model_folder(*key_den)

            def _process_model_folder(path):

                select_model_den(key_den)
                plugin.progress_bar.hide()

            worker = _get_model_folder()
            worker.returned.connect(_process_model_folder)
            worker.start()

            # delay showing progress bar -> won't show up if model already downloaded
            # TODO: hacky -> better way to do this?
            time.sleep(0.1)
            plugin.call_button.enabled = False
            plugin.progress_bar.label = 'Downloading Denoising model'
            plugin.progress_bar.show()

        else:
            select_model_den(key_den)

    # load config/thresholds from custom model path
    # -> triggered by _model_type_change
    # note: will be triggered at every keystroke (when typing the path)
    @change_handler(plugin.model_folder_star, init=False)
    def _model_star_folder_change(_path: str):
        path = Path(_path)
        key = CUSTOM_SEG_MODEL_STAR, path
        try:
            if not path.is_dir():
                return
            model_star_configs[key] = load_json(str(path / 'config.json'))
            model_star_threshs[key] = load_json(str(path / 'thresholds.json'))
        except FileNotFoundError:
            pass
        finally:
            select_model_star(key)

    @change_handler(plugin.model_folder_unet, init=False)
    def _model_unet_folder_change(_path: str):
        path = Path(_path)
        key = CUSTOM_SEG_MODEL_UNET, path
        try:
            if not path.is_dir():
                return
            model_unet_configs[key] = load_json(str(path / 'config.json'))
        except FileNotFoundError:
            pass
        finally:
            select_model_unet(key)

    @change_handler(plugin.model_folder_den, init=False)
    def _model_den_folder_change(_path: str):
        path = Path(_path)
        key = CUSTOM_DEN_MODEL, path
        try:
            if not path.is_dir():
                return
            model_den_configs[key] = load_json(str(path / 'config.json'))
        except FileNotFoundError:
            pass
        finally:
            select_model_den(key)

    # -------------------------------------------------------------------------

    # -> triggered by napari (if there are any open images on plugin launch)
    @change_handler(plugin.image, init=False)
    def _image_change(image: napari.layers.Image):
        ndim = get_data(image).ndim
        
        plugin.image.tooltip = f'Shape: {get_data(image).shape}'

        # dimensionality of selected model: 2, 3, or None (unknown)
        ndim_model = None
        if plugin.star_seg_model_type.value == StarDist2D:
            ndim_model = 2
        elif plugin.star_seg_model_type.value == StarDist3D:
            ndim_model = 3
        else:
            if model_selected_star in model_star_configs:
                config = model_star_configs[model_selected_star]
                ndim_model = config.get('n_dim')
                
            if model_selected_unet in model_unet_configs:
                config = model_unet_configs[model_selected_unet]
                ndim_model = config.get('n_dim')    
        #Force channel axes to be last
        
        # TODO: guess images axes better...
        axes = None
        if ndim == 2:
            axes = 'YX'
            plugin_star_parameters.n_tiles.value = (1,1)
        elif ndim == 3:
            axes = 'YXC' if image.rgb else ('ZYX' if ndim_model == 3 else 'TYX')
            plugin_star_parameters.n_tiles.value = (1,1,1)
        elif ndim == 4:
            axes = ('ZYXC' if ndim_model == 3 else 'TYXC') if image.rgb else 'TZYX'
            plugin_star_parameters.n_tiles.value = (1,1,1,1)
        else:
            raise NotImplementedError()
        
               
        
        if axes == plugin.axes.value:
            # make sure to trigger a changed event, even if value didn't actually change
            plugin.axes.changed(axes)
        else:
            plugin.axes.value = axes
        plugin_star_parameters.n_tiles.changed(plugin_star_parameters.n_tiles.value)
        plugin.norm_axes.changed(plugin.norm_axes.value)

    # -> triggered by _image_change
    @change_handler(plugin.axes, init=False)
    def _axes_change(value: str):
        if value != value.upper():
            with plugin.axes.changed.blocked():
                plugin.axes.value = value.upper()
        image = plugin.image.value
        axes = ''
        try:
            image is not None or _raise(ValueError('no image selected'))
            axes = axes_check_and_normalize(
                value, length=get_data(image).ndim, disallowed='S'
            )
            update('image_axes', True, (axes, image, None))
            update_unet('image_axes', True, (axes, image, None))
            update_den('image_axes', True, (axes, image, None))
        except ValueError as err:
            update('image_axes', False, (value, image, err))
            update_unet('image_axes', False, (value, image, err))
            update_den('image_axes', False, (value, image, err))
        # finally:
        # widgets_inactive(plugin.timelapse_opts, active=('T' in axes))

    # -> triggered by _image_change
    @change_handler(plugin_star_parameters.n_tiles, init=False)
    def _n_tiles_change():
        image = plugin.image.value
        try:
            image is not None or _raise(ValueError('no image selected'))
            value = plugin_star_parameters.n_tiles.get_value()
            if value is None:
                update('n_tiles', True, (None, image, None))
                update_unet('n_tiles', True, (None, image, None))
                update_den('n_tiles', True, (None, image, None))
                return
            shape = get_data(image).shape
            try:
                value = tuple(value)
                len(value) == len(shape) or _raise(TypeError())
            except TypeError:
                raise ValueError(f'must be a tuple/list of length {len(shape)}')
            if not all(isinstance(t, int) and t >= 1 for t in value):
                raise ValueError(f'each value must be an integer >= 1')
            update('n_tiles', True, (value, image, None))
            update_unet('n_tiles', True, (value, image, None))
            update_den('n_tiles', True, (value, image, None))
        except (ValueError, SyntaxError) as err:
            update('n_tiles', False, (None, image, err))
            update_unet('n_tiles', False, (None, image, err))
            update_den('n_tiles', False, (None, image, err))
    # -------------------------------------------------------------------------

    # set thresholds to optimized values for chosen model
    @change_handler(plugin_star_parameters.set_thresholds, init=False)
    def _set_thresholds():
        if model_selected_star in model_star_threshs:
            thresholds = model_star_threshs[model_selected_star]
            plugin.nms_thresh.value = thresholds['nms']
            plugin.prob_thresh.value = thresholds['prob']

    @change_handler(plugin_extra_parameters.min_size)
    def _min_size_change(value: float):

        plugin_extra_parameters.min_size.value = value
        
        
    @change_handler(plugin_extra_parameters.iouthresh)
    def _iou_thresh_change(value: float):

        plugin_extra_parameters.iouthresh.value = value     

    @change_handler(plugin_extra_parameters.min_size_mask)
    def _min_size_mask_change(value: float):
        plugin_extra_parameters.min_size_mask.value = value

    @change_handler(plugin_extra_parameters.max_size)
    def _max_size_change(value: float):
        plugin_extra_parameters.max_size.value = value

   

    # restore defaults
    @change_handler(plugin_star_parameters.defaults_star_parameters_button, init=False)
    def restore_star_param_defaults():
        for k, v in DEFAULTS_STAR_PARAMETERS.items():
            getattr(plugin_star_parameters, k).value = v

    @change_handler(
        plugin_extra_parameters.defaults_vollseg_parameters_button, init=False
    )
    def restore_vollseg_param_defaults():
        for k, v in DEFAULTS_VOLL_PARAMETERS.items():
            getattr(plugin_extra_parameters, k).value = v

    @change_handler(plugin.defaults_model_button, init=False)
    def restore_model_defaults():
        for k, v in DEFAULTS_MODEL.items():
            getattr(plugin, k).value = v

    # -------------------------------------------------------------------------

    # allow some widgets to shrink because their size depends on user input
    plugin.image.native.setMinimumWidth(120)
    plugin.model2d_star.native.setMinimumWidth(120)
    plugin.model3d_star.native.setMinimumWidth(120)

    plugin.model_unet.native.setMinimumWidth(120)

    plugin.model_den.native.setMinimumWidth(120)

    plugin.label_head.native.setOpenExternalLinks(True)
    # make reset button smaller
    # plugin.defaults_button.native.setMaximumWidth(150)

    # plugin.model_axes.native.setReadOnly(True)
    plugin.model_axes.enabled = False

    return plugin


def inrimage_file_reader(path):
    array = inrimage.read_inrimage(path)
    # return it as a list of LayerData tuples,
    # here with no optional metadata
    return [(array,)]


# def klbimage_file_reader(path):
# array = klb.read_klb(path)
# return it as a list of LayerData tuples,
# here with no optional metadata
# return [(array,)]


def tifimage_file_reader(path):
    array = imread(path)
    # return it as a list of LayerData tuples,
    # here with no optional metadata
    return [(array,)]


def h5image_file_reader(path):
    array = h5.read_h5(path)
    # return it as a list of LayerData tuples,
    # here with no optional metadata
    return [(array,)]


@napari_hook_implementation(specname='napari_get_reader')
def napari_get_reader(path: str):
    # If we recognize the format, we return the actual reader function
    if isinstance(path, str) and path.endswith('.inr') or path.endswith('.inr.gz'):
        return inrimage_file_reader
    # if isinstance(path, str) and path.endswith('.klb'):
    # return klbimage_file_reader
    if isinstance(path, str) and path.endswith('.tif'):
        return tifimage_file_reader
    if isinstance(path, str) and path.endswith('.h5'):
        return h5image_file_reader

    else:
        # otherwise we return None.
        return None


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    return plugin_wrapper_vollseg, dict(name='VollSeg', add_vertical_stretch=True)


@napari_hook_implementation
def napari_provide_sample_data():
    from stardist import data

    return {
        'test_image_cell_2d': {
            'data': lambda: [(data.test_image_nuclei_2d(), {'name': 'cell2d'})],
            'display_name': 'Cell (2D)',
        },
        'test_image_cell_3d': {
            'data': lambda: [(data.test_image_nuclei_3d(), {'name': 'cell3d'})],
            'display_name': 'Cell (3D)',
        },
    }
