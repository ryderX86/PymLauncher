import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import "."

View3D {
    anchors.fill: parent

    environment: SceneEnvironment {
        backgroundMode: SceneEnvironment.Transparent
    }

    Node {
        id: steveWrapper
        Steve {
            id: playerModel
            objectName: "steveModel"
            position: Qt.vector3d(0, -0.9, 0)
            rotation: Qt.quaternion(0, 0, 360, 0)
        }
    }

    DirectionalLight {z: 500}

    PerspectiveCamera {
        id: mainCam
        z: 3
        clipNear: 0.1
    }

    OrbitCameraController {
        camera: mainCam
        origin: steveWrapper
        mouseEnabled: true

        yInvert: false
        xInvert: true
    }
}