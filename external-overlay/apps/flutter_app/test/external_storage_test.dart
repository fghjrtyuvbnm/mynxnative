import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:flutter_app/models/game_info.dart';
import 'package:flutter_app/services/game_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('external directory authorization survives a game metadata round trip', () {
    final game = GameInfo.fromJson({
      'path': '/Volumes/Drive/Game',
      'title': 'Saved title',
      'externalDirectoryId': 'persistent-folder-id',
    });
    final saved = GameInfo.listFromJsonString(GameInfo.listToJsonString([game])).single;
    expect(saved.toJson()['externalDirectoryId'], 'persistent-folder-id');
    expect(saved.title, 'Saved title');
  });

  test('a restored mount path retains authorization and play history', () async {
    final manager = GameManager();
    await manager.addGame(GameInfo.fromJson({
      'path': '/Volumes/OldMount/Game',
      'externalDirectoryId': 'persistent-folder-id',
      'playDurationSeconds': 300,
    }));
    await manager.updateGamePath('/Volumes/OldMount/Game', '/Volumes/NewMount/Game');
    final reloaded = GameManager();
    await reloaded.load();
    expect(reloaded.games.single.path, '/Volumes/NewMount/Game');
    expect(reloaded.games.single.toJson()['externalDirectoryId'], 'persistent-folder-id');
    expect(reloaded.games.single.playDurationSeconds, 300);
  });

  test('legacy internal games load without requiring external authorization', () {
    final game = GameInfo.fromJson({'path': '/Documents/Games/Legacy'});
    expect(game.toJson()['externalDirectoryId'], isNull);
    expect(game.path, '/Documents/Games/Legacy');
  });
}
