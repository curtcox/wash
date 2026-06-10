import 'dart:io';
import 'dart:convert';

class PathSegmentError implements Exception {
  final String message;
  PathSegmentError(this.message);
  @override
  String toString() => 'PathSegmentError: $message';
}

class RootEscapeError implements Exception {
  final String message;
  RootEscapeError(this.message);
  @override
  String toString() => 'RootEscapeError: $message';
}

class SymlinkEscapeError implements Exception {
  final String message;
  SymlinkEscapeError(this.message);
  @override
  String toString() => 'SymlinkEscapeError: $message';
}

enum ResourceKind { file, directory }

class FilesystemResource {
  final ResourceKind kind;
  final String path;
  final String relPath;

  FilesystemResource(this.kind, this.path, this.relPath);
}

const Map<String, String> fallbackMimeTable = {
  '.html': 'text/html',
  '.htm': 'text/html',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.json': 'application/json',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.svg': 'image/svg+xml',
  '.xml': 'application/xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.pdf': 'application/pdf',
  '.wasm': 'application/wasm',
};
const String mimeDefault = 'application/octet-stream';
const List<String> defaultIndexNames = ['index.html'];

class EnvConfigError implements Exception {
  final String message;
  EnvConfigError(this.message);
  @override
  String toString() => 'EnvConfigError: $message';
}

class MimeConfig {
  final Map<String, String> mapping;
  final String? defaultType;

  MimeConfig(this.mapping, this.defaultType);
}

List<String> _envConfigLines(String path) {
  final file = File(path);
  if (!file.existsSync()) return <String>[];
  final lines = <String>[];
  for (final raw in file.readAsLinesSync()) {
    final stripped = raw.trim();
    if (stripped.isEmpty || stripped.startsWith('#')) continue;
    lines.add(stripped);
  }
  return lines;
}

MimeConfig loadMimeConfig(String root) {
  final path = '$root${Platform.pathSeparator}env${Platform.pathSeparator}mime';
  if (!File(path).existsSync()) return MimeConfig(<String, String>{}, null);
  final mapping = <String, String>{};
  String? defaultType;
  for (final line in _envConfigLines(path)) {
    final tokens = line.split(RegExp(r'\s+'));
    if (tokens.length != 2) {
      throw EnvConfigError('malformed env/mime line: $line');
    }
    final key = tokens[0];
    final mediaType = tokens[1];
    if (!mediaType.contains('/')) {
      throw EnvConfigError('malformed env/mime media type: $mediaType');
    }
    if (key == 'default') {
      defaultType = mediaType;
    } else if (key.startsWith('.') && key.length > 1) {
      mapping[key.toLowerCase()] = mediaType;
    } else {
      throw EnvConfigError('malformed env/mime suffix: $key');
    }
  }
  return MimeConfig(mapping, defaultType);
}

List<String> loadIndexNames(String root) {
  final path =
      '$root${Platform.pathSeparator}env${Platform.pathSeparator}index';
  if (!File(path).existsSync()) return List<String>.from(defaultIndexNames);
  final names = <String>[];
  for (final line in _envConfigLines(path)) {
    if (line.contains('/') ||
        line.contains('\\') ||
        line.contains('\x00') ||
        line == '.' ||
        line == '..') {
      throw EnvConfigError('malformed env/index entry: $line');
    }
    names.add(line);
  }
  return names;
}

bool listingEnabled(String root) {
  final path =
      '$root${Platform.pathSeparator}env${Platform.pathSeparator}listing';
  if (!File(path).existsSync()) return true;
  final lines = _envConfigLines(path);
  if (lines.length != 1 || (lines[0] != 'on' && lines[0] != 'off')) {
    throw EnvConfigError('malformed env/listing: expected single on/off token');
  }
  return lines[0] == 'on';
}

List<String> splitRawTarget(String rawTarget) {
  if (!rawTarget.startsWith('/')) {
    rawTarget = '/$rawTarget';
  }
  final parts = rawTarget.split('/');
  final segments = <String>[];
  for (final part in parts) {
    if (part.isEmpty) continue;
    segments.add(part);
  }
  return segments;
}

String percentDecodeSegment(String raw, {required bool forFilesystem}) {
  try {
    final decoded = Uri.decodeComponent(raw.replaceAll('+', '%2B'));
    if (forFilesystem && (decoded.contains('/') || decoded.contains('\x00'))) {
      throw PathSegmentError('decoded / or NUL in filesystem path segment');
    }
    return decoded;
  } on PathSegmentError {
    rethrow;
  } catch (e) {
    throw PathSegmentError(e.toString());
  }
}

List<String> normalizePathParts(List<String> parts) {
  final stack = <String>[];
  for (final part in parts) {
    if (part == '' || part == '.') continue;
    if (part == '..') {
      if (stack.isNotEmpty) {
        stack.removeLast();
      } else {
        stack.add('..');
      }
      continue;
    }
    stack.add(part);
  }
  return stack;
}

bool _isUnderRoot(String rootResolved, String pathResolved) {
  final sep = Platform.pathSeparator;
  return pathResolved == rootResolved ||
      pathResolved.startsWith(rootResolved + sep);
}

String? _lookupChild(
  String directory,
  String name, {
  required bool caseSensitive,
}) {
  final direct = '$directory${Platform.pathSeparator}$name';
  if (File(direct).existsSync() ||
      Link(direct).existsSync() ||
      Directory(direct).existsSync()) {
    return direct;
  }
  if (caseSensitive) return null;
  try {
    final dir = Directory(directory);
    for (final entry in dir.listSync(followLinks: false)) {
      if (entry.path.split(Platform.pathSeparator).last.toLowerCase() ==
          name.toLowerCase()) {
        return entry.path;
      }
    }
  } catch (_) {}
  return null;
}

String? _walkUnderRoot(
  String root,
  List<String> relParts, {
  required String symlinkPolicy,
  required bool caseSensitive,
}) {
  String current = root;
  for (final part in normalizePathParts(relParts)) {
    final dirStat = FileStat.statSync(current);
    if (dirStat.type != FileSystemEntityType.directory) return null;

    final next = _lookupChild(current, part, caseSensitive: caseSensitive);
    if (next == null) return null;

    final linkCheck = Link(next);
    if (linkCheck.existsSync()) {
      final target = linkCheck.resolveSymbolicLinksSync();
      if (symlinkPolicy == 'reject-escaping' && !_isUnderRoot(root, target)) {
        throw SymlinkEscapeError('symlink escapes root');
      }
      if (symlinkPolicy == 'unsupported') {
        throw SymlinkEscapeError('symlinks unsupported');
      }
      current = target;
    } else {
      current = next;
    }
  }
  final resolvedCurrent = _resolveReal(current);
  if (!_isUnderRoot(root, resolvedCurrent)) {
    throw RootEscapeError('path escapes root');
  }
  return current;
}

String _resolveReal(String path) {
  try {
    return File(path).resolveSymbolicLinksSync();
  } catch (_) {
    try {
      return Directory(path).resolveSymbolicLinksSync();
    } catch (_) {
      return path;
    }
  }
}

FilesystemResource? tryExactFilesystem(
  String root,
  List<String> rawSegments, {
  String symlinkPolicy = 'reject-escaping',
  bool caseSensitive = true,
}) {
  if (rawSegments.isEmpty) {
    if (Directory(root).existsSync()) {
      return FilesystemResource(ResourceKind.directory, root, '');
    }
    return null;
  }

  var fsSegments = List<String>.from(rawSegments);
  final last = fsSegments.last;
  if (last.contains('?')) {
    final qIdx = last.indexOf('?');
    final queryPart = last.substring(qIdx + 1);
    if (!queryPart.contains('/')) {
      final namePart = last.substring(0, qIdx);
      if (namePart.isEmpty) return null;
      fsSegments = List<String>.from(fsSegments)
        ..[fsSegments.length - 1] = namePart;
    }
  }

  final decodedParts = <String>[];
  for (final raw in fsSegments) {
    try {
      decodedParts.add(percentDecodeSegment(raw, forFilesystem: true));
    } on PathSegmentError {
      return null;
    }
  }

  String? resolved;
  try {
    resolved = _walkUnderRoot(
      root,
      decodedParts,
      symlinkPolicy: symlinkPolicy,
      caseSensitive: caseSensitive,
    );
  } on RootEscapeError {
    return null;
  } on SymlinkEscapeError {
    return null;
  }

  if (resolved == null) return null;

  final stat = FileStat.statSync(resolved);
  if (stat.type == FileSystemEntityType.notFound) return null;

  final rootResolved = _resolveReal(root);
  String rel;
  try {
    rel = resolved
        .replaceFirst(rootResolved, '')
        .replaceFirst(RegExp(r'^[/\\]'), '');
    rel = rel.replaceAll('\\', '/');
  } catch (_) {
    rel = '';
  }

  if (stat.type == FileSystemEntityType.directory) {
    return FilesystemResource(ResourceKind.directory, resolved, rel);
  }
  if (stat.type == FileSystemEntityType.file ||
      stat.type == FileSystemEntityType.link) {
    return FilesystemResource(ResourceKind.file, resolved, rel);
  }
  return null;
}

String inferMime(String path, {String? root}) {
  final dotIdx = path.lastIndexOf('.');
  final ext = dotIdx < 0 ? '' : path.substring(dotIdx).toLowerCase();
  if (root != null) {
    final config = loadMimeConfig(root);
    final mapped = config.mapping[ext];
    if (mapped != null) return mapped;
    if (config.defaultType != null) return config.defaultType!;
  }
  return fallbackMimeTable[ext] ?? mimeDefault;
}

String inferMimeFromBytes(List<int> data, String? declared) {
  if (declared != null && declared.isNotEmpty) return declared;
  if (data.isEmpty) return 'text/plain';
  try {
    utf8.decode(data);
    return 'text/plain';
  } catch (_) {
    return mimeDefault;
  }
}

List<int> readFileBytes(String path) {
  return File(path).readAsBytesSync();
}

List<int> directoryListing(String path) {
  final dir = Directory(path);
  final entries = dir.listSync(followLinks: false);
  entries.sort((a, b) {
    final aName = a.path.split(Platform.pathSeparator).last;
    final bName = b.path.split(Platform.pathSeparator).last;
    return aName.compareTo(bName);
  });
  final lines = <String>[];
  for (final entry in entries) {
    final name = entry.path.split(Platform.pathSeparator).last;
    final suffix = (entry is Directory) ? '/' : '';
    lines.add('$name$suffix');
  }
  final body = lines.isEmpty ? '' : '${lines.join('\n')}\n';
  return utf8.encode(body);
}

String? findIndexFile(String path, List<String> indexNames) {
  for (final name in indexNames) {
    final candidate = '$path${Platform.pathSeparator}$name';
    if (File(candidate).existsSync()) return candidate;
  }
  return null;
}

String putFile(
  String root,
  List<String> relParts,
  List<int> body, {
  bool createParents = true,
  String symlinkPolicy = 'reject-escaping',
}) {
  final rootResolved = _resolveReal(root);
  final normalized = normalizePathParts(relParts);
  if (normalized.isEmpty) {
    throw RootEscapeError('cannot PUT root directory');
  }

  String current = rootResolved;
  for (final part in normalized.sublist(0, normalized.length - 1)) {
    current = '$current${Platform.pathSeparator}$part';
    final link = Link(current);
    if (link.existsSync()) {
      final resolved = link.resolveSymbolicLinksSync();
      if (symlinkPolicy == 'reject-escaping' &&
          !_isUnderRoot(rootResolved, resolved)) {
        throw SymlinkEscapeError('symlink escapes root');
      }
    }
    if (!_isUnderRoot(rootResolved, current)) {
      throw RootEscapeError('path escapes root');
    }
  }

  final target = '$current${Platform.pathSeparator}${normalized.last}';
  final targetLink = Link(target);
  if (targetLink.existsSync()) {
    final resolved = targetLink.resolveSymbolicLinksSync();
    if (symlinkPolicy == 'reject-escaping' &&
        !_isUnderRoot(rootResolved, resolved)) {
      throw SymlinkEscapeError('symlink escapes root');
    }
  }
  if (!_isUnderRoot(rootResolved, target)) {
    throw RootEscapeError('path escapes root');
  }

  final targetFile = File(target);
  if (createParents) {
    targetFile.parent.createSync(recursive: true);
  } else if (!targetFile.parent.existsSync()) {
    throw FileSystemException('parent directory does not exist', target);
  }
  targetFile.writeAsBytesSync(body);
  return target;
}

void deleteFile(
  String root,
  List<String> relParts, {
  String symlinkPolicy = 'reject-escaping',
}) {
  final rootResolved = _resolveReal(root);
  String? resolved;
  try {
    resolved = _walkUnderRoot(
      rootResolved,
      relParts,
      symlinkPolicy: symlinkPolicy,
      caseSensitive: true,
    );
  } on RootEscapeError {
    rethrow;
  } on SymlinkEscapeError {
    rethrow;
  }
  if (resolved == null || !File(resolved).existsSync()) {
    throw FileSystemException('file not found', resolved ?? '');
  }
  File(resolved).deleteSync();
}

List<String> literalPathPartsFromRaw(List<String> rawSegments) {
  return rawSegments
      .map((raw) => percentDecodeSegment(raw, forFilesystem: true))
      .toList();
}

List<int> impliedCatBytes(
  String root,
  List<String> rawSegments, {
  String symlinkPolicy = 'reject-escaping',
  bool caseSensitive = true,
}) {
  if (rawSegments.isEmpty) return [];
  final rootResolved = _resolveReal(root);
  final fsParts = rawSegments
      .map((raw) => percentDecodeSegment(raw, forFilesystem: true))
      .toList();

  String? resolved;
  try {
    resolved = _walkUnderRoot(
      rootResolved,
      fsParts,
      symlinkPolicy: symlinkPolicy,
      caseSensitive: caseSensitive,
    );
  } on RootEscapeError {
    throw FileSystemException('input suffix escapes root');
  } on SymlinkEscapeError {
    throw FileSystemException('input suffix symlink escapes root');
  }

  if (resolved == null) {
    throw FileSystemException('input suffix not found');
  }
  final stat = FileStat.statSync(resolved);
  if (stat.type == FileSystemEntityType.directory) {
    throw FileSystemException('input suffix is a directory');
  }
  return File(resolved).readAsBytesSync();
}
