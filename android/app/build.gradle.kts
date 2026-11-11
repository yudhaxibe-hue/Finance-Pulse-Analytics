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
        val propVersionCode = (project.findProperty("versionCode") as String?)?.toIntOrNull() ?: 16
        val propVersionName = (project.findProperty("versionName") as String?) ?: "1.2.0"
        versionCode = propVersionCode
        versionName = propVersionName

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
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
