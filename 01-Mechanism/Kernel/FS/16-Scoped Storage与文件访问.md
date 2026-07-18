# Scoped Storage 与文件访问

## 学习目标

- 理解 Scoped Storage 设计理念
- 掌握 MediaStore API 的使用
- 理解 Storage Access Framework (SAF)
- 了解 DocumentsProvider 实现
- 理解应用文件访问权限模型

## 概述

Scoped Storage 是 Android 10 引入的新存储模型，旨在提供更好的隐私保护和更严格的权限控制。

---

## 一、Scoped Storage 设计理念

### 设计目标

1. **隐私保护**：应用只能访问自己的文件
2. **权限简化**：减少存储权限的使用
3. **数据隔离**：应用数据相互隔离
4. **向后兼容**：逐步迁移，保持兼容

### 存储范围

```
应用存储范围：

┌─────────────────────────────────────────────────────────────┐
│  应用私有目录（无需权限）                                    │
│  /data/data/<package>/                                      │
│  ├── files/        # 内部存储                               │
│  ├── cache/        # 缓存                                   │
│  └── databases/    # 数据库                                 │
├─────────────────────────────────────────────────────────────┤
│  应用外部存储目录（无需权限）                                │
│  /storage/emulated/0/Android/data/<package>/               │
│  ├── files/        # 外部存储                               │
│  └── cache/        # 外部缓存                               │
├─────────────────────────────────────────────────────────────┤
│  媒体文件（通过 MediaStore）                                 │
│  /storage/emulated/0/DCIM/                                 │
│  /storage/emulated/0/Pictures/                             │
│  /storage/emulated/0/Music/                                │
├─────────────────────────────────────────────────────────────┤
│  其他文件（通过 SAF）                                        │
│  需要用户选择                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、MediaStore API

### MediaStore 概述

MediaStore 是访问媒体文件的标准 API，替代直接文件路径访问。

### MediaStore 使用

```java
// 查询图片
ContentResolver resolver = getContentResolver();
Uri collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;

String[] projection = {
    MediaStore.Images.Media._ID,
    MediaStore.Images.Media.DISPLAY_NAME,
    MediaStore.Images.Media.DATE_ADDED
};

String selection = MediaStore.Images.Media.DATE_ADDED + " >= ?";
String[] selectionArgs = {String.valueOf(timestamp)};

Cursor cursor = resolver.query(collection, projection, selection, selectionArgs, null);
```

### MediaStore 插入

```java
// 插入图片
ContentValues values = new ContentValues();
values.put(MediaStore.Images.Media.DISPLAY_NAME, "image.jpg");
values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
values.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES);

Uri uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);

// 写入文件
try (OutputStream out = resolver.openOutputStream(uri)) {
    bitmap.compress(Bitmap.CompressFormat.JPEG, 100, out);
}
```

---

## 三、Storage Access Framework (SAF)

### SAF 概述

SAF 允许用户选择文件或目录，提供统一的文件访问接口。

### SAF 使用

```java
// 打开文档
Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
intent.addCategory(Intent.CATEGORY_OPENABLE);
intent.setType("image/*");
startActivityForResult(intent, REQUEST_CODE);

// 处理结果
@Override
protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    if (resultCode == RESULT_OK && data != null) {
        Uri uri = data.getData();
        // 使用 uri 访问文件
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            // 读取文件
        }
    }
}
```

### DocumentsProvider 实现

```java
// 自定义 DocumentsProvider
public class MyDocumentsProvider extends DocumentsProvider {
    @Override
    public Cursor queryRoots(String[] projection) {
        // 返回根目录
    }
    
    @Override
    public Cursor queryDocument(String documentId, String[] projection) {
        // 返回文档信息
    }
    
    @Override
    public ParcelFileDescriptor openDocument(String documentId,
                                             String mode,
                                             CancellationSignal signal) {
        // 打开文档
    }
}
```

---

## 四、应用文件访问权限模型

### 权限类型

| 权限 | 说明 | 适用范围 |
|-----|------|---------|
| 无权限 | 访问应用私有目录 | Android 10+ |
| READ_EXTERNAL_STORAGE | 读取媒体文件 | Android 10-12 |
| WRITE_EXTERNAL_STORAGE | 写入媒体文件 | Android 10-12 |
| MANAGE_EXTERNAL_STORAGE | 管理所有文件 | 特殊应用 |

### 权限申请

```java
// Android 10+ 权限申请
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
    // 无需权限访问应用目录
    // 需要权限访问其他应用文件
    if (shouldShowRequestPermissionRationale(Manifest.permission.READ_EXTERNAL_STORAGE)) {
        // 显示说明
    }
    requestPermissions(new String[]{
        Manifest.permission.READ_EXTERNAL_STORAGE
    }, REQUEST_CODE);
}
```

---

## 总结

### 核心要点

1. **Scoped Storage**：
   - 应用数据隔离
   - 更好的隐私保护
   - 简化的权限模型

2. **MediaStore API**：
   - 访问媒体文件的标准方式
   - 替代直接文件路径

3. **SAF**：
   - 用户选择文件
   - 统一的文件访问接口

### 后续学习

- [文件权限与安全机制](17-文件权限与安全机制.md) - 深入理解权限模型
- [文件系统调试与问题排查](20-文件系统调试与问题排查.md) - 调试方法

## 参考资源

- Android 源码：
  - `frameworks/base/core/java/android/provider/MediaStore.java`
  - `frameworks/base/core/java/android/provider/DocumentsProvider.java`

## 更新记录

- 2026-01-28：初始创建，包含 Scoped Storage 与文件访问详解
