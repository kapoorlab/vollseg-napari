import numpy as np
from tifffile import imwrite
import pytest

from vollseg import UNET, StarDist3D, StarDist2D,CARE
from typing import List, Union
from vollseg_napari import _test_dock_widget
import napari
from csbdeep.utils import load_json
from vollseg.pretrained import  get_model_folder
from vollseg import VollSeg
def test_defaults(make_napari_viewer):

    fake_plugin_master = _test_dock_widget.plugin_wrapper_vollseg()
    fake_plugin, fake_plugin_star_parameters, fake_plugin_extra_parameters, fake_plugin_display_parameters,  fake_plugin_stop_parameters, get_data = fake_plugin_master
    fake_viewer = make_napari_viewer()
    fake_viewer.open_sample(plugin='vollseg-napari', sample='carcinoma_cells_3dt')
    
    image = get_data(fake_viewer.layers[0])[2,:]

    name = 'test_3d'
    fake_viewer.add_image(image, name = name )
    
    #Test the pre-trained models if they are compatiable with the images they are supposed to work on 
    fake_plugin_star_parameters.n_tiles.value = (1,4,4,4)
    fake_plugin.axes.value = 'ZYX'
    fake_plugin.den_model_type.value ='NODEN'
    fake_plugin.star_seg_model_type.value = StarDist3D
    fake_plugin.unet_seg_model_type.value ='NOUNET'
    fake_plugin.roi_model_type.value ='NOROI'
    fake_plugin.model3d_star.value = 'Carcinoma_cells'
    key_star = fake_plugin.star_seg_model_type.value, fake_plugin.model3d_star.value
    model_path = get_model_folder( fake_plugin.star_seg_model_type.value, fake_plugin.model3d_star.value)
    model_star = fake_plugin.star_seg_model_type.value(None, name=fake_plugin.model3d_star.value, basedir=str(model_path).removesuffix(fake_plugin.model3d_star.value))
    path = str(model_path) + '/' + 'config.json'
    model_star_configs = dict()
    model_star_configs[key_star] = load_json(path)
    config_star = model_star_configs.get(key_star)
    axes_star = config_star.get(
                            'axes', 'ZYXC'[-len(config_star['net_input_shape']) :])
    
        
    key_den = fake_plugin.den_model_type.value, fake_plugin.model_den.value    
    fake_plugin.den_model_type.value = CARE    
    fake_plugin.model_den.value = 'Denoise_carcinoma'
    model_den_configs = dict()
    model_path = get_model_folder(fake_plugin.den_model_type.value, fake_plugin.model_den.value)
    model_den = fake_plugin.den_model_type.value(None, name=fake_plugin.model_den.value, basedir=str(model_path).removesuffix(fake_plugin.model_den.value))
    path = str(model_path) + '/' + 'config.json'
    model_den_configs = dict()
    model_den_configs[key_den] = load_json(path)
    config_den = model_den_configs.get(key_den)
    axes_den = config_den.get(
                            'axes', 'ZYXC'[-len(config_den['unet_input_shape']) :])
   
    valid = update(fake_plugin_star_parameters, model_star, model_den, image )

    assert valid == True 

def update(fake_plugin_star_parameters, star_model, noise_model, image ):


    res = VollSeg(image, star_model = star_model, noise_model = noise_model,  n_tiles = fake_plugin_star_parameters.n_tiles.value)
    if len(res) == 7:
      valid = True
    else:
      valid = False

    return valid