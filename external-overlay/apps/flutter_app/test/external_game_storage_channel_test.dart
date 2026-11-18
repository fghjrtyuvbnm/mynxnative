import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_app/models/game_info.dart';
import 'package:flutter_app/services/external_game_storage.dart';
import 'package:flutter_app/services/game_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('flutter_engine_bridge');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test('cancelling the directory picker returns no game', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'pickExternalGameDirectory');
      return null;
    });
    expect(await ExternalGameStorage.pickDirectory(), isNull);
  });

  test('a disconnected folder remains registered and reconnects by bookmark ID', () async {
    final manager = GameManager();
    await manager.addGame(GameInfo.fromJson({
      'path': '/Volumes/Old/Game',
      'externalDirectoryId': 'folder-id',
      'title': 'My Game',
      'playDurationSeconds': 120,
    }));
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'restoreExternalGameDirectories');
      expect(call.arguments, ['folder-id']);
      return [];
    });
    expect(await ExternalGameStorage.restore(['folder-id']), isEmpty);
    final reloaded = GameManager();
    await reloaded.load();
    expect(reloaded.games.single.title, 'My Game');
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'activateExternalGameDirectory');
      expect(call.arguments, 'folder-id');
      return '/Volumes/New/Game';
    });
    final path = await ExternalGameStorage.activate('folder-id');
    await reloaded.updateGamePath(reloaded.games.single.path, path);
    await reloaded.addGame(GameInfo(path: path, externalDirectoryId: 'folder-id'));
    expect(reloaded.games, hasLength(1));
    expect(reloaded.games.single.playDurationSeconds, 120);
    expect(reloaded.games.single.externalDirectoryId, 'folder-id');
  });

  test('denied storage access reaches the launcher as an error', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      throw PlatformException(code: 'directory_unavailable');
    });
    await expectLater(
      ExternalGameStorage.activate('folder-id'),
      throwsA(isA<PlatformException>()),
    );
  });

  test('selecting a moved folder preserves its existing game entry', () async {
    final manager = GameManager();
    await manager.addGame(GameInfo(
      path: '/Old/Game', externalDirectoryId: 'folder-id',
      title: 'Keep this title',
    ));
    final added = await manager.addGame(GameInfo(
      path: '/New/Game', externalDirectoryId: 'folder-id',
    ));
    expect(added, isFalse);
    expect(manager.games, hasLength(1));
    expect(manager.games.single.path, '/New/Game');
    expect(manager.games.single.title, 'Keep this title');
  });
}
