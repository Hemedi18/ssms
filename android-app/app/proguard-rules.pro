# Retrofit & Gson rules
-dontwarn okhttp3.**
-dontwarn okio.**
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.simsms.gateway.data.api.models.** { *; }
-keep class com.simsms.gateway.data.local.entities.** { *; }
