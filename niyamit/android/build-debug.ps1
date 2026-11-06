param(
 [string]$Sdk = "D:\Android\Sdk",
 [string]$Jdk = "D:\androidstd\jbr",
 [string]$AppUrl = "http://localhost:3000/"
)
$ErrorActionPreference = "Stop"
$env:JAVA_HOME = $Jdk
$project = $PSScriptRoot
$out = Join-Path $project "build"
$tools = Join-Path $Sdk "build-tools\36.0.0"
$platform = Join-Path $Sdk "platforms\android-37.0\android.jar"
$parsedUrl = [Uri]$AppUrl
if (-not $parsedUrl.IsAbsoluteUri -or $parsedUrl.UserInfo -or $parsedUrl.Query -or $parsedUrl.Fragment -or ($parsedUrl.Scheme -ne "https" -and $AppUrl -notmatch '^http://(localhost|10\.0\.2\.2):3000/?$')) { throw "Use an HTTPS app origin, or localhost:3000 for emulator debug." }
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Android build tool failed: $LASTEXITCODE" } }
New-Item -ItemType Directory -Force $out,"$out/res/values","$out/res/drawable","$out/res/xml","$out/gen","$out/classes","$out/dex" | Out-Null
Copy-Item "$project/app/src/main/res/drawable/logo.xml" "$out/res/drawable/logo.xml"
Copy-Item "$project/app/src/main/res/xml/network_security_config.xml" "$out/res/xml/network_security_config.xml"
$escaped = [System.Security.SecurityElement]::Escape($AppUrl)
[IO.File]::WriteAllText("$out/res/values/config.xml", "<resources><string name=`"app_url`">$escaped</string></resources>")
$manifest = [IO.File]::ReadAllText("$project/app/src/main/AndroidManifest.xml").Replace('${cleartext}', 'true').Replace('<manifest ', '<manifest package="com.niyamit.app" ').Replace('<application ', '<application android:debuggable="true" ')
[IO.File]::WriteAllText("$out/AndroidManifest.xml",$manifest)
& "$tools/aapt2.exe" compile --dir "$out/res" -o "$out/resources.zip"; Check-Exit
& "$tools/aapt2.exe" link -o "$out/resources.apk" -I $platform --manifest "$out/AndroidManifest.xml" --java "$out/gen" --min-sdk-version 29 --target-sdk-version 36 --version-code 1 --version-name "0.1-demo" "$out/resources.zip"; Check-Exit
$sources = @(Get-ChildItem "$project/app/src/main/java","$out/gen" -Recurse -Filter *.java | ForEach-Object {$_.FullName})
& "$Jdk/bin/javac.exe" -encoding UTF-8 -source 8 -target 8 -bootclasspath "$platform;$tools/core-lambda-stubs.jar" -d "$out/classes" @sources; Check-Exit
& "$Jdk/bin/jar.exe" cf "$out/classes.jar" -C "$out/classes" .; Check-Exit
& "$tools/d8.bat" --lib $platform --min-api 29 --output "$out/dex" "$out/classes.jar"; Check-Exit
Copy-Item "$out/resources.apk" "$out/unsigned.apk" -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open("$out/unsigned.apk",[IO.Compression.ZipArchiveMode]::Update)
try { [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,"$out/dex/classes.dex","classes.dex") | Out-Null } finally { $archive.Dispose() }
& "$tools/zipalign.exe" -f 4 "$out/unsigned.apk" "$out/aligned.apk"; Check-Exit
# Public Android debug credentials, never a release signing identity.
$key = Join-Path $project "debug.keystore"
if (-not (Test-Path -LiteralPath $key)) {
 & "$Jdk/bin/keytool.exe" -genkeypair -keystore $key -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"; Check-Exit
}
& "$tools/apksigner.bat" sign --ks $key --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out "$out/Niyamit-debug.apk" "$out/aligned.apk"; Check-Exit
& "$tools/apksigner.bat" verify --verbose "$out/Niyamit-debug.apk"; Check-Exit
Write-Output "Built debug APK: $out/Niyamit-debug.apk"
