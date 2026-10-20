"""Finite real glTF geometry, not a renderer or a replacement scene provider."""
import hashlib
import json
import math
import re
import struct

def specification(run):
    if not isinstance(run, str) or not re.fullmatch('[0-9a-f]{32}', run):
        raise ValueError('Original Owner 32-hex challenge required')
    nonce = bytes.fromhex(run)
    return {'scale': .84 + .12 * nonce[0] / 255,
            'y': -.08 + .16 * nonce[1] / 255,
            'translate_x': .55 + .1 * nonce[2] / 255,
            'camera_z': 3., 'camera_fov': math.pi / 3}

def asset(run):
    spec = specification(run)
    scale, shift = spec['scale'], spec['y']
    positions = [(-.85, -.5), (-.15, -.5), (-.15, .5), (-.85, .5),
                 (.15, -.5), (.95, -.5), (.55, .5)]
    vertices = [(x * scale, y * scale + shift, 0.) for x, y in positions]
    payload = struct.pack('<21f', *(v for p in vertices for v in p))
    payload += struct.pack('<9H', 0, 1, 2, 0, 2, 3, 0, 1, 2)
    document = {
        'asset': {'version': '2.0', 'generator': 'openharmony QEMU Graphics3D audit geometry'},
        'extensionsUsed': ['KHR_materials_unlit'],
        'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'name': 'AuditAsset', 'children': [1, 2]},
                  {'name': 'AuditRed', 'mesh': 0}, {'name': 'AuditGreen', 'mesh': 1}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 2, 'material': 0}]},
                   {'primitives': [{'attributes': {'POSITION': 1}, 'indices': 3, 'material': 1}]}],
        'materials': [{'name': name, 'doubleSided': True,
                       'pbrMetallicRoughness': {'baseColorFactor': color, 'metallicFactor': 0,
                                                'roughnessFactor': 1},
                       'extensions': {'KHR_materials_unlit': {}}}
                      for name, color in [('Red', [1, 0, 0, 1]), ('Green', [0, 1, 0, 1])]],
        'buffers': [{'byteLength': len(payload)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 84, 'target': 34962},
                        {'buffer': 0, 'byteOffset': 84, 'byteLength': 18, 'target': 34963}],
        'accessors': [
            {'bufferView': 0, 'byteOffset': offset, 'componentType': 5126,
             'count': len(ps), 'type': 'VEC3',
             'min': [min(p[i] for p in ps) for i in range(3)],
             'max': [max(p[i] for p in ps) for i in range(3)]}
            for offset, ps in [(0, vertices[:4]), (48, vertices[4:])]] + [
            {'bufferView': 1, 'byteOffset': offset, 'componentType': 5123,
             'count': count, 'type': 'SCALAR'} for offset, count in [(0, 6), (12, 3)]]}
    json_chunk = json.dumps(document, separators=(',', ':'), allow_nan=False).encode()
    json_chunk += b' ' * (-len(json_chunk) % 4)
    bin_chunk = payload + b'\0' * (-len(payload) % 4)
    size = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return (struct.pack('<4sII', b'glTF', 2, size) +
            struct.pack('<II', len(json_chunk), 0x4E4F534A) + json_chunk +
            struct.pack('<II', len(bin_chunk), 0x004E4942) + bin_chunk)

def invalid_asset():
    # Correct container header; deliberately invalid JSON syntax in its JSON chunk.
    return struct.pack('<4sIIII', b'glTF', 2, 24, 4, 0x4E4F534A) + b'{bad'

def descriptors(run):
    return {name: {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
            for name, content in [('graphics3d-audit.glb', asset(run)),
                                  ('graphics3d-invalid.glb', invalid_asset())]}
