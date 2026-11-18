import 'package:flutter/services.dart';

/// An authorized folder is identified independently of its mount path.
class ExternalGameDirectory {
  const ExternalGameDirectory(this.id, this.path);

  final String id;
  final String path;

  factory ExternalGameDirectory.fromMap(Map<Object?, Object?> value) =>
      ExternalGameDirectory(value['id'] as String, value['path'] as String);
}

class ExternalGameStorage {
  static const _channel = MethodChannel('flutter_engine_bridge');

  static Future<ExternalGameDirectory?> pickDirectory() async {
    final value = await _channel.invokeMapMethod<Object?, Object?>(
      'pickExternalGameDirectory',
    );
    return value == null ? null : ExternalGameDirectory.fromMap(value);
  }

  static Future<List<ExternalGameDirectory>> restore(List<String> ids) async {
    final values = await _channel.invokeListMethod<Object?>(
      'restoreExternalGameDirectories', ids,
    );
    return (values ?? []).map((value) =>
      ExternalGameDirectory.fromMap(value as Map<Object?, Object?>)).toList();
  }

  static Future<String> activate(String id) async {
    final path = await _channel.invokeMethod<String>(
      'activateExternalGameDirectory', id,
    );
    if (path == null) {
      throw PlatformException(code: 'directory_unavailable');
    }
    return path;
  }

  static Future<void> forget(String id) =>
      _channel.invokeMethod<void>('forgetExternalGameDirectory', id);
}
