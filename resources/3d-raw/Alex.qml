import QtQuick
import QtQuick3D

import QtQuick.Timeline

Node {
    id: node

    // Resources
    property url textureData: "maps/textureData.png"
    property url textureData31: "maps/textureData31.png"
    Texture {
        id: _0_texture
        tilingModeHorizontal: Texture.ClampToEdge
        tilingModeVertical: Texture.ClampToEdge
        magFilter: Texture.Nearest
        minFilter: Texture.Nearest
        generateMipmaps: true
        mipFilter: Texture.Linear
        source: node.textureData
    }
    Texture {
        id: _1_texture
        tilingModeHorizontal: Texture.ClampToEdge
        tilingModeVertical: Texture.ClampToEdge
        magFilter: Texture.Nearest
        minFilter: Texture.Nearest
        generateMipmaps: true
        mipFilter: Texture.Linear
        source: node.textureData31
    }
    PrincipledMaterial {
        id: principledMaterial
        baseColorMap: _0_texture
        roughness: 1
        cullMode: PrincipledMaterial.NoCulling
        alphaMode: PrincipledMaterial.Mask
        depthDrawMode: PrincipledMaterial.OpaquePrePassDepthDraw
        alphaCutoff: 0.05000000074505806
    }
    PrincipledMaterial {
        id: principledMaterial29
        baseColorMap: _1_texture
        roughness: 1
        cullMode: PrincipledMaterial.NoCulling
        alphaMode: PrincipledMaterial.Mask
        depthDrawMode: PrincipledMaterial.OpaquePrePassDepthDraw
        alphaCutoff: 0.05000000074505806
    }

    // Nodes:
    Node {
        id: root
        objectName: "ROOT"
        Node {
            id: waist
            objectName: "Waist"
            position: Qt.vector3d(0, 0.75, 0)
            Node {
                id: head
                objectName: "Head"
                position: Qt.vector3d(0, 0.75, 0)
                Model {
                    id: head4
                    objectName: "Head"
                    position: Qt.vector3d(0, -1.5, 0)
                    source: "meshes/meshes_0__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
                Model {
                    id: hat_Layer
                    objectName: "Hat Layer"
                    position: Qt.vector3d(0, -1.5, 0)
                    source: "meshes/meshes_1__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
            }
            Node {
                id: body
                objectName: "Body"
                position: Qt.vector3d(0, 0.75, 0)
                Model {
                    id: body12
                    objectName: "Body"
                    position: Qt.vector3d(0, -1.5, 0)
                    source: "meshes/meshes_2__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
                Model {
                    id: body_Layer
                    objectName: "Body Layer"
                    position: Qt.vector3d(0, -1.5, 0)
                    source: "meshes/meshes_3__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
            }
            Node {
                id: right_Arm
                objectName: "Right Arm"
                position: Qt.vector3d(0.3125, 0.625, 0)
                rotation: Qt.quaternion(0.999762, 0, 0, 0.0218149)
                Model {
                    id: right_Arm17
                    objectName: "Right Arm"
                    position: Qt.vector3d(-0.3125, -1.375, 0)
                    source: "meshes/meshes_4__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
                Model {
                    id: right_Arm_Layer
                    objectName: "Right Arm Layer"
                    position: Qt.vector3d(-0.3125, -1.375, 0)
                    source: "meshes/meshes_5__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
            }
            Node {
                id: left_Arm
                objectName: "Left Arm"
                position: Qt.vector3d(-0.3125, 0.625, 0)
                rotation: Qt.quaternion(0.999762, 0, 0, -0.0218149)
                Model {
                    id: left_Arm22
                    objectName: "Left Arm"
                    position: Qt.vector3d(0.375, -1.375, 0)
                    source: "meshes/meshes_6__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
                Model {
                    id: left_Arm_Layer
                    objectName: "Left Arm Layer"
                    position: Qt.vector3d(0.375, -1.375, 0)
                    source: "meshes/meshes_7__mesh.mesh"
                    materials: [
                        principledMaterial
                    ]
                }
            }
            Node {
                id: cape
                objectName: "cape"
                position: Qt.vector3d(0, 0.75, 0.125)
                Model {
                    id: cape27
                    objectName: "cape"
                    rotation: Qt.quaternion(0.999048, -0.0436194, 0, 0)
                    source: "meshes/meshes_8__mesh.mesh"
                    materials: [
                        principledMaterial29
                    ]
                }
            }
        }
        Node {
            id: right_Leg
            objectName: "Right Leg"
            position: Qt.vector3d(0.11875, 0.75, 0)
            Model {
                id: right_Leg33
                objectName: "Right Leg"
                position: Qt.vector3d(-0.11875, -0.75, 0)
                source: "meshes/meshes_9__mesh.mesh"
                materials: [
                    principledMaterial
                ]
            }
            Model {
                id: right_Leg_Layer
                objectName: "Right Leg Layer"
                position: Qt.vector3d(-0.11875, -0.75, 0)
                source: "meshes/meshes_10__mesh.mesh"
                materials: [
                    principledMaterial
                ]
            }
        }
        Node {
            id: left_Leg
            objectName: "Left Leg"
            position: Qt.vector3d(-0.11875, 0.75, 0)
            Model {
                id: left_Leg38
                objectName: "Left Leg"
                position: Qt.vector3d(0.11875, -0.75, 0)
                source: "meshes/meshes_11__mesh.mesh"
                materials: [
                    principledMaterial
                ]
            }
            Model {
                id: left_Leg_Layer
                objectName: "Left Leg Layer"
                position: Qt.vector3d(0.11875, -0.75, 0)
                source: "meshes/meshes_12__mesh.mesh"
                materials: [
                    principledMaterial
                ]
            }
        }
    }

    // Animations:
    Timeline {
        id: walk_timeline
        objectName: "walk"
        property real framesPerSecond: 1000
        startFrame: 0
        endFrame: 4000
        currentFrame: 0
        enabled: true
        animations: TimelineAnimation {
            duration: 4000
            from: 0
            to: 4000
            running: true
            loops: Animation.Infinite
        }
        KeyframeGroup {
            target: right_Arm
            property: "rotation"
            keyframeSource: "animations/right_Arm_rotation_0.qad"
        }
        KeyframeGroup {
            target: left_Arm
            property: "rotation"
            keyframeSource: "animations/left_Arm_rotation_0.qad"
        }
        KeyframeGroup {
            target: right_Leg
            property: "rotation"
            keyframeSource: "animations/right_Leg_rotation_0.qad"
        }
        KeyframeGroup {
            target: left_Leg
            property: "rotation"
            keyframeSource: "animations/left_Leg_rotation_0.qad"
        }
        KeyframeGroup {
            target: cape
            property: "rotation"
            keyframeSource: "animations/cape_rotation_0.qad"
        }
    }
}
