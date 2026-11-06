package com.niyamit.app;

import android.Manifest;
import android.app.*;
import android.os.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.provider.MediaStore;
import android.view.*;
import android.webkit.*;
import android.widget.*;
import java.util.ArrayList;

public class MainActivity extends Activity {
 private WebView web;
 private LinearLayout root;
 private TextView status;
 private String start;
 private PermissionRequest pendingAudio;
 private ValueCallback<Uri[]> fileCallback;
 private Uri cameraOutput;
 private static final int FILE=10, AUDIO=11;
 private boolean sameOrigin(Uri uri) {
  Uri origin=Uri.parse(start);
  return origin.getScheme().equals(uri.getScheme()) && origin.getHost().equals(uri.getHost()) && origin.getPort()==uri.getPort();
 }
 private void openExternal(Uri uri) {
  if (!java.util.Arrays.asList("https","http","tel","mailto").contains(uri.getScheme())) return;
  try {startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(ActivityNotFoundException e){Toast.makeText(this,"No app can open this link.",Toast.LENGTH_SHORT).show();}
 }
 @Override public void onCreate(Bundle state) {
  super.onCreate(state);start=getString(R.string.app_url);
  root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Color.WHITE);
  root.setOnApplyWindowInsetsListener((v,insets)->{if(Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);}else{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());}return insets;});
  LinearLayout toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(12,0,12,0);
  Button home=new Button(this);home.setText("Niyamit");home.setOnClickListener(v->web.loadUrl(start));toolbar.addView(home);
  status=new TextView(this);status.setText("Patient + Clinic");toolbar.addView(status,new LinearLayout.LayoutParams(0,48,1));
  Button retry=new Button(this);retry.setText("Reload");retry.setOnClickListener(v->web.reload());toolbar.addView(retry);root.addView(toolbar);
  WebView.setWebContentsDebuggingEnabled((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0);
  web=new WebView(this);root.addView(web,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
  WebSettings ws=web.getSettings();ws.setJavaScriptEnabled(true);ws.setDomStorageEnabled(true);ws.setAllowFileAccess(false);ws.setAllowContentAccess(false);ws.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);ws.setMediaPlaybackRequiresUserGesture(true);
  CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
  // No JavascriptInterface is exposed to remote pages.
  web.setWebViewClient(new WebViewClient(){
   @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest req){if(sameOrigin(req.getUrl()))return false;openExternal(req.getUrl());return true;}
   @Override public void onPageStarted(WebView v,String url,android.graphics.Bitmap icon){status.setText("Loading...");}
   @Override public void onPageFinished(WebView v,String url){status.setText("Patient + Clinic");CookieManager.getInstance().flush();}
   @Override public void onReceivedError(WebView v,WebResourceRequest req,WebResourceError error){if(req.isForMainFrame()){status.setText("Connection unavailable");Toast.makeText(MainActivity.this,"The Niyamit server is unavailable. Check internet and tap Reload.",Toast.LENGTH_LONG).show();}}
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("Confirm",(d,w)->result.confirm()).setNegativeButton("Cancel",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();return true;}

   @Override public void onPermissionRequest(PermissionRequest req){runOnUiThread(()->{
    if(!sameOrigin(req.getOrigin()) || !java.util.Arrays.asList(req.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)){req.deny();return;}
    if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED)req.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
    else {if(pendingAudio!=null)pendingAudio.deny();pendingAudio=req;requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},AUDIO);}
   });}
   @Override public void onPermissionRequestCanceled(PermissionRequest req){if(pendingAudio==req)pendingAudio=null;}
   @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> cb,FileChooserParams params){
    if(fileCallback!=null)fileCallback.onReceiveValue(null);fileCallback=cb;
    try {
     Intent pick;
     if(params.isCaptureEnabled() && java.util.Arrays.toString(params.getAcceptTypes()).contains("image")){
      ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,"niyamit-scan-"+System.currentTimeMillis()+".jpg");values.put(MediaStore.Images.Media.MIME_TYPE,"image/jpeg");
      cameraOutput=getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);
      pick=new Intent(MediaStore.ACTION_IMAGE_CAPTURE);pick.putExtra(MediaStore.EXTRA_OUTPUT,cameraOutput);pick.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_READ_URI_PERMISSION);
     } else {pick=new Intent(Intent.ACTION_GET_CONTENT);pick.addCategory(Intent.CATEGORY_OPENABLE);pick.setType("*/*");String[] accepts=params.getAcceptTypes();if(accepts.length>0&&!accepts[0].isEmpty())pick.putExtra(Intent.EXTRA_MIME_TYPES,accepts);pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,false);}
     startActivityForResult(pick,FILE);return true;
    }catch(Exception e){if(cameraOutput!=null){getContentResolver().delete(cameraOutput,null,null);cameraOutput=null;}fileCallback.onReceiveValue(null);fileCallback=null;Toast.makeText(MainActivity.this,"No file or camera app available.",Toast.LENGTH_LONG).show();return true;}
   }
  });
  web.setDownloadListener((url,ua,disposition,mime,length)->{
   if(!sameOrigin(Uri.parse(url)))return;
   DownloadManager.Request req=new DownloadManager.Request(Uri.parse(url));String cookie=CookieManager.getInstance().getCookie(url);if(cookie!=null)req.addRequestHeader("Cookie",cookie);req.addRequestHeader("User-Agent",ua);
   req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);req.setDestinationInExternalFilesDir(this,Environment.DIRECTORY_DOWNLOADS,"niyamit-original-"+System.currentTimeMillis()+("application/pdf".equals(mime)?".pdf":".bin"));
   try{((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(req);Toast.makeText(this,"Downloading original to Niyamit app files.",Toast.LENGTH_LONG).show();}catch(Exception e){Toast.makeText(this,"Could not download original.",Toast.LENGTH_LONG).show();}
  });
  if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,()->{if(web.canGoBack())web.goBack();else finish();});
  if(state==null || web.restoreState(state)==null)web.loadUrl(start);
 }
 @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results){super.onRequestPermissionsResult(code,permissions,results);if(code==AUDIO&&pendingAudio!=null){if(results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED)pendingAudio.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});else pendingAudio.deny();pendingAudio=null;}}
 @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(req==FILE&&fileCallback!=null){Uri[] uris=null;if(result==RESULT_OK)uris=cameraOutput!=null?new Uri[]{cameraOutput}:WebChromeClient.FileChooserParams.parseResult(result,data);else if(cameraOutput!=null)getContentResolver().delete(cameraOutput,null,null);cameraOutput=null;fileCallback.onReceiveValue(uris);fileCallback=null;}}
 @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
 @Override protected void onSaveInstanceState(Bundle state){web.saveState(state);super.onSaveInstanceState(state);}
 @Override protected void onDestroy(){if(pendingAudio!=null)pendingAudio.deny();if(fileCallback!=null)fileCallback.onReceiveValue(null);web.destroy();super.onDestroy();}
}
