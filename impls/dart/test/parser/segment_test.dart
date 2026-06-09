import 'package:test/test.dart';
import 'package:wash_server/parser/parser.dart';
import 'package:wash_server/filesystem/filesystem.dart';

void main() {
  group('splitRawTarget', () {
    test('splits simple path', () {
      expect(splitRawTarget('/a/b/c'), equals(['a', 'b', 'c']));
    });

    test('collapses leading slash', () {
      expect(splitRawTarget('/foo'), equals(['foo']));
    });

    test('collapses trailing slash', () {
      expect(splitRawTarget('/foo/'), equals(['foo']));
    });

    test('collapses repeated slashes', () {
      expect(splitRawTarget('//a//b//'), equals(['a', 'b']));
    });

    test('empty path returns empty list', () {
      expect(splitRawTarget('/'), equals([]));
    });
  });

  group('parseSegment', () {
    test('strips leading ampersand pre-decode', () {
      final seg = parseSegment('&grep');
      expect(seg.stderrMerge, isTrue);
      expect(seg.name, equals('grep'));
    });

    test('no ampersand means no stderr merge', () {
      final seg = parseSegment('grep');
      expect(seg.stderrMerge, isFalse);
      expect(seg.name, equals('grep'));
    });

    test('query items parsed correctly', () {
      final seg = parseSegment('grep?arg=-i&arg=needle');
      expect(seg.queryItems.length, equals(2));
      expect(seg.queryItems[0], equals(('arg', '-i')));
      expect(seg.queryItems[1], equals(('arg', 'needle')));
    });

    test('percent-encoded name decoded', () {
      final seg = parseSegment('foo%20bar');
      expect(seg.name, equals('foo bar'));
    });

    test('%26 in name is not stderr merge prefix', () {
      final seg = parseSegment('%26cmd');
      expect(seg.stderrMerge, isFalse);
      expect(seg.name, equals('&cmd'));
    });
  });

  group('coreArgvFromQuery', () {
    test('returns null when no arg keys', () {
      final items = [('pattern', 'needle')];
      expect(coreArgvFromQuery(items), isNull);
    });

    test('returns list of arg values', () {
      final items = [('arg', '-i'), ('arg', 'needle')];
      expect(coreArgvFromQuery(items), equals(['-i', 'needle']));
    });

    test('returns empty list when arg key present but empty', () {
      final items = [('arg', '')];
      expect(coreArgvFromQuery(items), equals(['']));
    });
  });

  group('percentDecodeSegment', () {
    test('decodes percent-encoded chars', () {
      expect(
          percentDecodeSegment('foo%20bar', forFilesystem: false),
          equals('foo bar'));
    });

    test('decodes slash for non-filesystem', () {
      expect(
          percentDecodeSegment('a%2Fb', forFilesystem: false),
          equals('a/b'));
    });

    test('throws PathSegmentError for decoded slash in filesystem mode', () {
      expect(
          () => percentDecodeSegment('a%2Fb', forFilesystem: true),
          throwsA(isA<PathSegmentError>()));
    });

    test('throws PathSegmentError for decoded NUL in filesystem mode', () {
      expect(
          () => percentDecodeSegment('a%00b', forFilesystem: true),
          throwsA(isA<PathSegmentError>()));
    });
  });

  group('normalizePathParts', () {
    test('removes dot segments', () {
      expect(normalizePathParts(['a', '.', 'b']), equals(['a', 'b']));
    });

    test('resolves double dot', () {
      expect(normalizePathParts(['a', 'b', '..', 'c']), equals(['a', 'c']));
    });

    test('handles leading double dot', () {
      expect(normalizePathParts(['..', 'a']), equals(['..', 'a']));
    });
  });
}
