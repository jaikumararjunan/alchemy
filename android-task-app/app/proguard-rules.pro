# Add project specific ProGuard rules here.

# Keep Room database classes
-keep class com.alchemy.taskapp.data.** { *; }

# Keep MediaPipe classes
-keep class com.google.mediapipe.** { *; }
-dontwarn com.google.mediapipe.**

# Keep ML Kit classes
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**

# Keep Hilt generated code
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }

# Kotlin serialization
-keepattributes *Annotation*
-keepclassmembers class ** {
    @com.google.gson.annotations.SerializedName <fields>;
}

# Keep enums (used for Room type converters)
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}
