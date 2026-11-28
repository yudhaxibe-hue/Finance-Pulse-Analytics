plugins {
    id("com.android.application")
}

android {
    namespace = "com.financepulse.analytics"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.financepulse.analytics"
        minSdk = 26
        targetSdk = 34
        val propVersionCode = (project.findProperty("versionCode") as String?)?.toIntOrNull() ?: 29
        val propVersionName = (project.findProperty("versionName") as String?) ?: "1.3.8"
        versionCode = propVersionCode
        versionName = propVersionName

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            val ksPath = System.getenv("ANDROID_KEYSTORE_FILE")
            if (!ksPath.isNullOrBlank()) {
                storeFile = file(ksPath)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: ""
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: ""
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD") ?: ""
            }
        }
    }

    buildTypes {
        release {
            val ksPath = System.getenv("ANDROID_KEYSTORE_FILE")
            if (!ksPath.isNullOrBlank()) {
                signingConfig = signingConfigs.getByName("release")
            }
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
