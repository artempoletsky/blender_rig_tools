import bpy
import os
from . import preferences
from .map_bones import BoneMapping
from mathutils import Vector, Matrix, geometry
import math
from . import bone_functions as b_fun
import re

oops = bpy.ops.object
aops = bpy.ops.armature

saved_x_axises = {}
saved_y_axises = {}
saved_z_axises = {}



def get_vertices_in_vgroup(object, vgroup_name, min_weight = 0.01):
    if not vgroup_name in object.vertex_groups:
        return []
    v_group = object.vertex_groups[vgroup_name]
    index = v_group.index
    vertices = []
    for v in object.data.vertices:
        found = False
        for g in v.groups:
            if g.group == index and g.weight > min_weight:
                found = True
                break
        if found:
            vertices.append(v)
    return vertices

def get_foot_end(object, toe_bone_name):
    end = float('inf')
    verts = get_vertices_in_vgroup(object, toe_bone_name)
    for v in verts:
        end = min(end, v.co.y)
    if end == float('inf'):
        return None
    return end

def get_foot_sides_back(object, foot_bone_name, suffix):
    side1 = float('inf')
    side2 = -float('inf')
    back = -float('inf')
    verts = get_vertices_in_vgroup(object, foot_bone_name)
    for v in verts:
        side1 = min(side1, v.co.x)
        side2 = max(side2, v.co.x)
        back = max(back, v.co.y)
    if side1 == float('inf'):
        side1 = None
    if side2 == -float('inf'):
        side2 = None
    if back == -float('inf'):
        back = None
    if suffix == 'R':
        temp = side1
        side1 = side2
        side2 = temp
    return side1, side2, back

def save_axises(armature):
    oops.mode_set(mode = 'EDIT')
    for bone in armature.edit_bones:
        saved_x_axises[bone.name] = bone.x_axis.copy()
        saved_y_axises[bone.name] = bone.y_axis.copy()
        saved_z_axises[bone.name] = bone.z_axis.copy()
    oops.mode_set(mode = 'OBJECT')


def copy_rotation_from_parent(edit_bone):
    parent = edit_bone.parent
    if not parent.parent:
        return

    q1 = parent.parent.matrix.to_quaternion()
    q2 = parent.matrix.to_quaternion()
    q_diff = q1.rotation_difference(q2)

    edit_bone.matrix =  edit_bone.matrix @ q_diff.to_matrix().to_4x4()


def get_bone(armature, bone_name, mapping = None):
    if mapping:
        bone_name = mapping.get_name(bone_name)
    if not bone_name in armature.bones:
        return None
    return armature.bones[bone_name]

def get_bone_position(armature, bone_name, mapping = None, head = True):
    bone = get_bone(armature, bone_name, mapping)
    if not bone:
        return None
    return Vector(bone.head_local if head else bone.tail_local)

saved_rigify_types = {}
def save_rigify_type(bone_name, type, fk_layer, tweak_layer):
    result = {}
    saved_rigify_types[bone_name] = result
    result['rigify_type'] = type
    result['fk_layer'] = fk_layer
    result['tweak_layer'] = tweak_layer
    return result

def set_rigify_types(object):
    pose_bones = object.pose.bones
    for bone_name, rigify_type in saved_rigify_types.items():
        bone = pose_bones[bone_name]
        for key, value in rigify_type.items():
            bone.rigify_parameters.bbones = 1
            if key == 'rigify_type':
                bone.rigify_type = value
            # elif key == 'copy_rotaion_axes':
            #     b_fun.set_array_indices(bone.rigify_parameters.copy_rotation_axes, value)
            elif key == 'tweak_layer':
                b_fun.set_array_indices(bone.rigify_parameters.tweak_layers, [value])
            elif key == 'fk_layer':
                b_fun.set_array_indices(bone.rigify_parameters.fk_layers, [value])
            else:
                setattr(bone.rigify_parameters, key, value)

def create_tentakle(spine_arr, source_armature, object, layer = 0):
    bones = create_bone_chain(spine_arr, source_armature, object, layer = layer)
    is_tail = bool(re.findall(r'(?i)tail', spine_arr[0]))
    rigify_type = 'spines.basic_tail' if is_tail else 'limbs.simple_tentacle'

    rigify_parameters = save_rigify_type(bones[0].name, rigify_type, layer + 1, layer + 1)
    rigify_parameters['copy_rotation_axes'] = [True, False, True]
    return bones, rigify_parameters

EX_BONES = []

def create_bone_chain(spine_arr, source_armature, object, layer = 0):
    # print(spine_arr)
    target_armature = object.data
    # b_fun.set_array_indices(target_armature.layers, [layer])
    b_fun.switch_to_layer(target_armature, layer)
    spine_len = len(spine_arr)
    source_bones = source_armature.bones
    target_bones = target_armature.edit_bones

    parent = None
    if not spine_arr[0] in source_bones:
        return []
    parent_name = source_bones[spine_arr[0]].parent.name if source_bones[spine_arr[0]].parent else None
    created_bones = []

    for i in range(spine_len):
        head_bone_name = spine_arr[i]
        head_bone = get_bone(source_armature, head_bone_name)
        if head_bone is None:
            print(spine_arr[i] + ' passed head')
            break
        head = head_bone.head_local

        q_diff = None

        tail = None
        if i < spine_len - 1:
            tail = get_bone_position(source_armature, spine_arr[i + 1])

        if tail is None:
            tail = head_bone.tail_local

        target_bone = target_bones.new(spine_arr[i])

        target_bone.head = head
        target_bone.tail = tail

        created_bones.append(target_bone)
        EX_BONES.append(target_bone.name)

        if parent:
            target_bone.parent = parent
            target_bone.use_connect = True
        elif parent_name and parent_name in target_bones:
            target_bone.parent = target_bones[parent_name]
            target_bone.use_connect = False

        parent = target_bone

    last_bone = parent

    if last_bone and last_bone.parent:
        parent = last_bone.parent
        align_bone_to_vector(last_bone, last_bone.parent.vector)
        # y_vec = parent.vector
        # y_vec.normalize()
        # tail = head + y_vec * head_bone.length

    return created_bones

def align_bone_to_vector(edit_bone, vector):
    edit_bone.tail = edit_bone.head + vector.normalized() * edit_bone.length

def align_bone_to_point(edit_bone, point):
    vector = point - edit_bone.head
    align_bone_to_vector(edit_bone, vector)

def add_single_bone(name, source_armature, object, direction_bone_name = None, layer = 0, fk_layer_offset = 1, tweak_layer_offset = 1, direction_vector = None):
    target_armature = object.data
    b_fun.switch_to_layer(target_armature, layer)
    source_bone = get_bone(source_armature, name)
    if not source_bone:
        print(name + ' passed')
        return None, None

    parent_name = source_bone.parent.name if source_bone.parent else None

    bone = target_armature.edit_bones.new(name)
    bone.head = source_bone.head_local
    bone.tail = source_bone.tail_local

    if direction_bone_name:
        align_bone_to_point(bone, get_bone_position(source_armature, direction_bone_name))
    elif direction_vector:
        align_bone_to_vector(bone, direction_vector)

    if parent_name:
        if parent_name in target_armature.edit_bones:
            bone.parent = target_armature.edit_bones[parent_name]

    # b_fun.align_bone_x_axis(bone, saved_y_axises[name])

    rigify_parameters = save_rigify_type(bone.name, 'basic.super_copy', layer + fk_layer_offset, layer + tweak_layer_offset)
    EX_BONES.append(bone.name)
    return bone, rigify_parameters

def get_spine_bones(source_armature):
    child = source_armature.bones['spine']
    result = []
    while child:
        result.append(child.name)
        children = child.children
        child = None
        for c in children:
            if c.name.startswith('spine'):
                child = c
                break
    return result

def create_spine(source_armature, object, head_chain_length):
    spine = get_spine_bones(source_armature)
    if len(spine) < 6 or len(spine) > 7:
        raise Exception("Can't create a spine. Only 6 or 7 length spines are supported.")
    bones = create_bone_chain(spine, source_armature, object, layer = 3)
    align_bone_to_vector(bones[-1], Vector((0, 0, 1)))

    for bone in bones:
        b_fun.align_bone_x_axis(bone, Vector((1, 0, 0)))

    save_rigify_type(bones[0].name, 'spines.basic_spine', 4, 4)
    bones[-head_chain_length].use_connect = False
    save_rigify_type(bones[-head_chain_length].name, 'spines.super_head', 4, 4)


def get_finger_end_point(object, vgroup_name, bone_head):
    verts = get_vertices_in_vgroup(object, vgroup_name)
    v_group = object.vertex_groups[vgroup_name]
    coord = bone_head.copy()
    max_d = 0

    for v in verts:
        max_d = max(max_d, (v.co - bone_head).length)

    for v in verts:
        dir = v.co - bone_head
        # print(v_group.weight(v.index))
        # print(dir.length / max_d)
        coord += dir * v_group.weight(v.index) * pow(dir.length / max_d, 10)
        # coord += v.co * v_group.weight(v.index) * (v.co - bone_head).length / max_d
    # coord = coord / len(verts)
    return coord

def get_finger_axis(armature, finger, suffix):
    f_name = finger.name.rstrip(suffix)
    if f_name == 'index_01_':
        neigbour = 'middle_01_' + suffix
    elif f_name == 'middle_01_':
        neigbour = 'ring_01_' + suffix
    elif f_name == 'ring_01_':
        neigbour = 'pinky_01_' + suffix
    elif f_name == 'pinky_01_':
        neigbour = 'ring_01_' + suffix
    elif f_name == 'thumb_01_':
        neigbour = 'index_01_' + suffix

    n_pos = get_bone_position(armature, neigbour)
    axis = n_pos - finger.head
    if f_name == 'pinky_01_':
        axis = -axis
    # v1 = n_pos - finger.head
    # v2 = finger.vector

    return axis

def create_thumb(suffix, source_object, object, palm_coord, palm_normal):
    source_armature = source_object.data
    spine = ['thumb.01.' + suffix, 'thumb.02.' + suffix, 'thumb.03.' + suffix]
    bones = create_bone_chain(spine, source_armature, object, layer = 5)
    if not bones:
        return
    if suffix == 'R':
        palm_normal = - palm_normal
    point = palm_coord + palm_normal / 8

    for bone in bones:
        z_axis = point - bone.tail
        vec = -z_axis.cross(bone.vector)
        b_fun.align_bone_x_axis(bone, vec)

    params = save_rigify_type('thumb.01.' + suffix, 'limbs.super_finger', 6, 6)
    params['primary_rotation_axis'] = 'X'


def create_finger(name, suffix, source_object, object, palm_coord, palm_normal):
    source_armature = source_object.data
    spine = [name + '.01.' + suffix, name + '.02.' + suffix, name + '.03.' + suffix]
    bones = create_bone_chain(spine, source_armature, object, layer = 5)
    if not bones:
        return
    if suffix == 'R':
        palm_normal = - palm_normal
    point = palm_coord + palm_normal
    for bone in bones:
        z_axis = point - bone.tail
        vec = -z_axis.cross(bone.vector)
        b_fun.align_bone_x_axis(bone, vec)

    params = save_rigify_type(name + '.01.' + suffix, 'limbs.super_finger', 6, 6)
    params['primary_rotation_axis'] = 'X'

scene_scale = {
    'scale': 1
}
def create_leg(suffix, source_object, object, layer = 0):
    source_armature = source_object.data
    spine = ['thigh.' + suffix, 'shin.' + suffix, 'foot.' + suffix, 'toe.' + suffix]
    bones = create_bone_chain(spine, source_armature, object, layer = layer)

    if len(bones) != 4:
        raise Exception('Can\'t create leg (' + suffix + ')')

    heel_width = 0.05 / scene_scale['scale']
    # print(scene_scale)
    heel_x = bones[1].tail.x
    heel_y = bones[1].tail.y
    heel_x = heel_x - heel_width if suffix == 'L' else heel_x + heel_width
    heel_width = heel_width * 2 if suffix == 'L' else -2 * heel_width

    if len(source_object.children):
        side1, side2, back = get_foot_sides_back(source_object.children[0], 'foot.' + suffix, suffix)
        if back:
            heel_y = back
        if side1 and side2:
            heel_x = side1
            heel_width = side2 - side1


    heel = object.data.edit_bones.new('heel.'+suffix.upper())
    heel.use_connect = False
    heel.parent = bones[2]
    heel.head = Vector((heel_x, heel_y, 0))
    heel.tail = Vector((heel_x + heel_width, heel_y, 0))

    b_fun.align_bone_x_axis(bones[0], Vector((1, 0, 0)))
    b_fun.align_bone_x_axis(bones[1], Vector((1, 0, 0)))

    if len(source_object.children):
        foot_end = get_foot_end(source_object.children[0], 'toe.' + suffix)
        toe_bone = bones[-1]
        if not foot_end:
            align_bone_to_vector(toe_bone, Vector((0, -1, 0)))
        else:
            toe_bone.tail.y = foot_end
            toe_bone.tail.z = bones[-1].head.z
            toe_bone.tail.x = bones[-1].head.x

    foot_bone = bones[-2]

    b_fun.align_bone_x_axis(foot_bone, Vector((1, 0, 0)))

    # print(foot_end)
    params = save_rigify_type('thigh.' + suffix, 'limbs.super_limb', layer + 1, layer + 2)
    params['limb_type'] = 'leg'
    params['rotation_axis'] = 'x'

    # adding twist bones to exclude list even if we don't create them
    EX_BONES.append('thigh.' + suffix + '.001')
    EX_BONES.append('shin.' + suffix + '.001')

def create_arm(suffix, source_armature, object, palm_no, layer = 0):
    spine = ['upper_arm.' + suffix, 'forearm.' + suffix, 'hand.' + suffix]
    bones = create_bone_chain(spine, source_armature, object, layer = layer)
    if len(bones) != 3:
        raise Exception('Can\'t create arm (' + suffix + ')')

    # b_fun.align_bone_x_axis(bones[1], -saved_z_axises[bones[1].name])
    # b_fun.align_bone_x_axis(bones[0], -saved_z_axises[bones[0].name])
    middle = get_bone_position(source_armature, 'f_middle.01.' + suffix)
    if middle:
        align_bone_to_point(bones[-1], middle)
    else:
        align_bone_to_vector(bones[-1], bones[-2].vector)
    for bone in bones:
        # vec = Vector((0, 0, -1)) if suffix == 'L' else Vector((0, 0, 1))
        # TODO: compute normal of the arm
        vec = -bone.tail if suffix == 'L' else bone.tail
        if bone.name.startswith('hand') and palm_no:
            vec = palm_no
        b_fun.align_bone_x_axis(bone, vec)
    EX_BONES.append('upper_arm.' + suffix + '.001')
    EX_BONES.append('forearm.' + suffix + '.001')
    params = save_rigify_type('upper_arm.' + suffix, 'limbs.super_limb', layer + 1, layer + 2)
    params['rotation_axis'] = 'x'

def compute_palm(source_armature, suffix):
    h = get_bone_position(source_armature, 'hand.' + suffix)
    r = get_bone_position(source_armature, 'f_ring.01.' + suffix)
    i = get_bone_position(source_armature, 'f_index.01.' + suffix)
    m = get_bone_position(source_armature, 'f_middle.01.' + suffix)
    if not h:
        return None, None
    if not r or not i or not m:
        hand = get_bone(source_armature, 'hand.' + suffix )
        return (hand.head + hand.tail) / 2, hand.x_axis
    palm_co = (h + m) / 2
    palm_no = -geometry.normal((h, i, r))
    palm_no *= (h - m).length * 1
    return palm_co, palm_no


def detect_bone_chains(bones):
    bones = [b for b in bones if b.name not in EX_BONES]
    chains = []
    for b in bones:
        if not b.parent:
            continue
        # root of the chain
        if b.parent.name in EX_BONES:
            parent = b
            chain = [b.name]
            chains.append(chain)
            while len(parent.children):
                parent = parent.children[0]
                chain.append(parent.name)

    return chains


class GenerateMetarigOperator(bpy.types.Operator):
    """Select an armature. Operator will create new metarig from the armature."""
    bl_idname = "object.ocr_generate_metarig"
    bl_label = "Generate metarig from armature"
    bl_options = {'REGISTER', 'UNDO'}

    head_chain_length: bpy.props.IntProperty(default = 2)

    @classmethod
    def poll(cls, context):
        return (context.space_data.type == 'VIEW_3D'
            # and len(context.selected_objects) > 0
            and context.view_layer.objects.active
            and context.object.type == 'ARMATURE'
            and (context.object.mode == 'OBJECT'))

    def execute(self, context):
        location = context.object.location
        source_object = context.object
        source_armature = context.object.data

        scene_scale['scale'] = context.scene.unit_settings.scale_length
        # print(scene_scale)
        EX_BONES.clear()
        EX_BONES.append('root')


        # save_axises(source_armature)

        oops.select_all(action = 'DESELECT')
        oops.armature_add(enter_editmode = True, align='WORLD', location = location)
        aops.select_all(action = 'SELECT')
        aops.delete()

        context.object.show_in_front = True
        context.object.name = 'metarig'
        context.object.data.show_axes = True

        bpy.ops.pose.rigify_layer_init()
        bpy.ops.armature.rigify_add_bone_groups()
        create_layers(context.object.data)

        try:
            create_spine(source_armature, context.object, self.head_chain_length)

            bone, params = add_single_bone('shoulder.L', source_armature, context.object, direction_bone_name = 'upper_arm.L', layer = 3)
            global_z_axis = Vector((0, 0, 1))
            if bone:
                b_fun.align_bone_x_axis(bone, -global_z_axis.cross(bone.vector))
                params['make_widget'] = False
            else:
                raise Exception('Can\'t create shoulder.L bone')
            bone, params = add_single_bone('shoulder.R', source_armature, context.object, direction_bone_name = 'upper_arm.R', layer = 3)
            if bone:
                b_fun.align_bone_x_axis(bone, -global_z_axis.cross(bone.vector))
                params['make_widget'] = False
            else:
                raise Exception('Can\'t create shoulder.R bone')

            bone, params = add_single_bone('breast.L', source_armature, context.object, layer = 3, direction_vector = Vector((0, -1, 0)))
            if bone:
                b_fun.align_bone_x_axis(bone, Vector((-1, 0, 0)))
            bone, params = add_single_bone('breast.R', source_armature, context.object, layer = 3, direction_vector = Vector((0, -1, 0)))
            if bone:
                b_fun.align_bone_x_axis(bone, Vector((-1, 0, 0)))

            co, no = compute_palm(source_armature, 'L')
            create_arm('L', source_armature, context.object, no, layer = 7)

            create_thumb('L', source_object, context.object, co, no)

            create_finger('f_index', 'L', source_object, context.object, co, no)
            create_finger('f_middle', 'L', source_object, context.object, co, no)
            create_finger('f_ring', 'L', source_object, context.object, co, no)
            create_finger('f_pinky', 'L', source_object, context.object, co, no)

            co, no = compute_palm(source_armature, 'R')
            create_arm('R', source_armature, context.object, no, layer = 10)

            create_thumb('R', source_object, context.object, co, no)
            create_finger('f_index', 'R', source_object, context.object, co, no)
            create_finger('f_middle', 'R', source_object, context.object, co, no)
            create_finger('f_ring', 'R', source_object, context.object, co, no)
            create_finger('f_pinky', 'R', source_object, context.object, co, no)

            create_leg('L', source_object, context.object, layer = 13)
            create_leg('R', source_object, context.object, layer = 16)
        except Exception as e:
            self.report({'ERROR'}, e.args[0])
            return {'FINISHED'}


        # return {'FINISHED'}




        for bone in source_armature.bones:
            if bone.name.startswith('ik'):
                EX_BONES.append(bone.name)

        chains = detect_bone_chains(source_armature.bones)
        # print(chains)
        for c in chains:
            if len(c) == 1:
                add_single_bone(c[0], source_armature, context.object, layer = 3)
            else:
                create_tentakle(c, source_armature, context.object, layer = 3 )

        b_fun.set_array_indices(context.object.data.layers, [0, 3, 5, 7, 10, 13, 16])
        oops.mode_set(mode = 'POSE')
        set_rigify_types(context.object)
        oops.mode_set(mode = 'OBJECT')
        # mapping.rename_armature(context.object.data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)

def create_layers(arm):
    arm.rigify_layers[0].name = 'Face'
    arm.rigify_layers[0].row = 1
    arm.rigify_layers[0].group = 5

    arm.rigify_layers[1].name = 'Face (Primary)'
    arm.rigify_layers[1].row = 2
    arm.rigify_layers[1].group = 2

    arm.rigify_layers[2].name = 'Face (Secondary)'
    arm.rigify_layers[2].row = 2
    arm.rigify_layers[2].group = 3


    arm.rigify_layers[3].name = 'Torso'
    arm.rigify_layers[3].row = 3
    arm.rigify_layers[3].group = 3

    arm.rigify_layers[4].name = 'Torso (Tweak)'
    arm.rigify_layers[4].row = 4
    arm.rigify_layers[4].group = 4

    arm.rigify_layers[5].name = 'Fingers'
    arm.rigify_layers[5].row = 5
    arm.rigify_layers[5].group = 6

    arm.rigify_layers[6].name = 'Fingers (Detail)'
    arm.rigify_layers[6].row = 6
    arm.rigify_layers[6].group = 5

    arm.rigify_layers[7].name = 'Arm.L (IK)'
    arm.rigify_layers[7].row = 7
    arm.rigify_layers[7].group = 2
    arm.rigify_layers[8].name = 'Arm.L (FK)'
    arm.rigify_layers[8].row = 8
    arm.rigify_layers[8].group = 5
    arm.rigify_layers[9].name = 'Arm.L (Tweak)'
    arm.rigify_layers[9].row = 9
    arm.rigify_layers[9].group = 4

    arm.rigify_layers[10].name = 'Arm.R (IK)'
    arm.rigify_layers[10].row = 7
    arm.rigify_layers[10].group = 2
    arm.rigify_layers[11].name = 'Arm.R (FK)'
    arm.rigify_layers[11].row = 8
    arm.rigify_layers[11].group = 5
    arm.rigify_layers[12].name = 'Arm.R (Tweak)'
    arm.rigify_layers[12].row = 9
    arm.rigify_layers[12].group = 4

    arm.rigify_layers[13].name = 'Leg.L (IK)'
    arm.rigify_layers[13].row = 10
    arm.rigify_layers[13].group = 2
    arm.rigify_layers[14].name = 'Leg.L (FK)'
    arm.rigify_layers[14].row = 11
    arm.rigify_layers[14].group = 5
    arm.rigify_layers[15].name = 'Leg.L (Tweak)'
    arm.rigify_layers[15].row = 12
    arm.rigify_layers[15].group = 4

    arm.rigify_layers[16].name = 'Leg.R (IK)'
    arm.rigify_layers[16].row = 10
    arm.rigify_layers[16].group = 2
    arm.rigify_layers[17].name = 'Leg.R (FK)'
    arm.rigify_layers[17].row = 11
    arm.rigify_layers[17].group = 5
    arm.rigify_layers[18].name = 'Leg.R (Tweak)'
    arm.rigify_layers[18].row = 12
    arm.rigify_layers[18].group = 4
    return
