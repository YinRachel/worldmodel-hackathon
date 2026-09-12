"""Validate manually entered room layout (centimetres)."""
import math


def validate_layout(data):
    limits={'room_width':(50,5000),'room_depth':(50,5000),'room_height':(100,1000),
            'sofa_width':(20,1000),'sofa_depth':(20,1000),'sofa_height':(10,500),
            'x':(-5000,10000),'y':(-5000,10000),'rotation':(0,359)}
    result={}
    for key,(low,high) in limits.items():
        value=data.get(key)
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'Invalid {key}: expected {low}–{high} cm (degrees for rotation).')
        result[key]=value
    for key in ('room_accuracy','sofa_accuracy'):
        if data.get(key) not in ('estimated','measured'):
            raise ValueError('Choose estimated or measured for both sets of dimensions.')
        result[key]=data[key]
    a=math.radians(result['rotation'])
    hx=(abs(math.cos(a))*result['sofa_width']+abs(math.sin(a))*result['sofa_depth'])/2
    hy=(abs(math.sin(a))*result['sofa_width']+abs(math.cos(a))*result['sofa_depth'])/2
    result['fits']=hx-1e-6<=result['x']<=result['room_width']-hx+1e-6 and hy-1e-6<=result['y']<=result['room_depth']-hy+1e-6 and result['sofa_height']<=result['room_height']
    return result
