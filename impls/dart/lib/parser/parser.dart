import 'dart:io';

import '../filesystem/filesystem.dart';
import '../metadata/metadata.dart';

class ParseError implements Exception {
  final String message;
  final int status;

  ParseError(this.message, {this.status = 400});

  @override
  String toString() => 'ParseError($status): $message';
}

class ParsedSegment {
  final String raw;
  final String name;
  final List<(String, String)> queryItems;
  final bool stderrMerge;

  ParsedSegment({
    required this.raw,
    required this.name,
    required this.queryItems,
    required this.stderrMerge,
  });
}

class CommandStage {
  final String name;
  final String commandPath;
  final List<String> argv;
  final CommandMetadata metadata;
  final bool stderrMergeBoundary;
  final String rawSegment;
  final bool argvFromQuery;

  CommandStage({
    required this.name,
    required this.commandPath,
    required this.argv,
    required this.metadata,
    required this.stderrMergeBoundary,
    required this.rawSegment,
    this.argvFromQuery = false,
  });
}

class PipelineParse {
  final List<CommandStage> stages;
  final List<String>? inputSuffixRaw;
  final String pipelineDescription;
  final String? sourcePath;

  PipelineParse({
    required this.stages,
    required this.inputSuffixRaw,
    this.pipelineDescription = '',
    this.sourcePath,
  });
}

class RawCommandParse {
  final CommandStage stage;
  final String rawSuffix;

  RawCommandParse({required this.stage, required this.rawSuffix});
}

class FilesystemParseResult {
  final FilesystemResource resource;
  FilesystemParseResult(this.resource);
}

class NotFoundParse {}

// Union type for parse results
sealed class ParseResult {}

class ParseResultFilesystem extends ParseResult {
  final FilesystemResource resource;
  ParseResultFilesystem(this.resource);
}

class ParseResultPipeline extends ParseResult {
  final PipelineParse pipeline;
  ParseResultPipeline(this.pipeline);
}

class ParseResultRaw extends ParseResult {
  final RawCommandParse raw;
  ParseResultRaw(this.raw);
}

class ParseResultNotFound extends ParseResult {}

ParsedSegment parseSegment(String raw) {
  var stderrMerge = false;
  var body = raw;
  if (body.startsWith('&')) {
    stderrMerge = true;
    body = body.substring(1);
  }

  String namePart;
  String queryPart;
  if (body.contains('?')) {
    final qIdx = body.indexOf('?');
    namePart = body.substring(0, qIdx);
    queryPart = body.substring(qIdx + 1);
  } else {
    namePart = body;
    queryPart = '';
  }

  final name = percentDecodeSegment(namePart, forFilesystem: false);
  final queryItems = <(String, String)>[];
  if (queryPart.isNotEmpty) {
    for (final pair in queryPart.split('&')) {
      if (pair.isEmpty) continue;
      final eqIdx = pair.indexOf('=');
      if (eqIdx < 0) {
        queryItems.add((Uri.decodeComponent(pair), ''));
      } else {
        final key = Uri.decodeComponent(pair.substring(0, eqIdx));
        final val = Uri.decodeComponent(pair.substring(eqIdx + 1));
        queryItems.add((key, val));
      }
    }
  }

  return ParsedSegment(
    raw: raw,
    name: name,
    queryItems: queryItems,
    stderrMerge: stderrMerge,
  );
}

List<String>? coreArgvFromQuery(List<(String, String)> queryItems) {
  final args = <String>[];
  var hasArgKey = false;
  for (final (key, value) in queryItems) {
    if (key == 'arg') {
      hasArgKey = true;
      args.add(value);
    }
  }
  if (!hasArgKey) return null;
  return args;
}

List<String> loadCommandPath(String root) {
  final pathFile = File('$root${Platform.pathSeparator}env${Platform.pathSeparator}path');
  final dirs = <String>[];
  if (!pathFile.existsSync()) return dirs;
  for (final line in pathFile.readAsLinesSync()) {
    final stripped = line.trim();
    if (stripped.isEmpty || stripped.startsWith('#')) continue;
    String p;
    if (stripped.startsWith('/')) {
      p = stripped;
    } else {
      p = '$root${Platform.pathSeparator}$stripped';
      p = Directory(p).absolute.path;
    }
    if (Directory(p).existsSync()) {
      dirs.add(p);
    }
  }
  return dirs;
}

String? resolveCommand(String name, List<String> commandDirs,
    {bool caseSensitive = true}) {
  for (final dir in commandDirs) {
    final candidate =
        '$dir${Platform.pathSeparator}$name';
    final stat = FileStat.statSync(candidate);
    if (stat.type == FileSystemEntityType.file ||
        stat.type == FileSystemEntityType.link) {
      return candidate;
    }
    if (!caseSensitive) {
      try {
        for (final entry in Directory(dir).listSync(followLinks: false)) {
          final entryName =
              entry.path.split(Platform.pathSeparator).last;
          if (entryName.toLowerCase() == name.toLowerCase()) {
            final s = FileStat.statSync(entry.path);
            if (s.type == FileSystemEntityType.file ||
                s.type == FileSystemEntityType.link) {
              return entry.path;
            }
          }
        }
      } catch (_) {}
    }
  }
  return null;
}

bool isCommand(String name, List<String> commandDirs,
    {bool caseSensitive = true}) {
  return resolveCommand(name, commandDirs, caseSensitive: caseSensitive) != null;
}

String _remainingRawSuffix(List<String> rawSegments, int start) {
  if (start >= rawSegments.length) return '';
  return rawSegments.sublist(start).join('/');
}

String formatPipeline(List<CommandStage> stages, List<String>? inputSuffix) {
  final parts = <String>[];
  if (inputSuffix != null && inputSuffix.isNotEmpty) {
    parts.add('cat ${inputSuffix.join('/')}');
  }
  for (final stage in stages.reversed) {
    var cmd = stage.name;
    if (stage.argv.isNotEmpty) {
      cmd += ' ${stage.argv.join(' ')}';
    }
    parts.add(cmd);
  }
  return parts.join(' | ');
}

ParseResult parseRequest(
  String method,
  String rawTarget,
  String root, {
  List<String>? commandDirs,
  bool caseSensitive = true,
  String symlinkPolicy = 'reject-escaping',
}) {
  commandDirs ??= loadCommandPath(root);

  String target = rawTarget.split('#')[0];
  final segments = splitRawTarget(target);

  final fs = tryExactFilesystem(
    root,
    segments,
    symlinkPolicy: symlinkPolicy,
    caseSensitive: caseSensitive,
  );
  if (fs != null) {
    return ParseResultFilesystem(fs);
  }

  if (segments.isEmpty) {
    return ParseResultNotFound();
  }

  final first = parseSegment(segments[0]);
  final firstPath =
      resolveCommand(first.name, commandDirs, caseSensitive: caseSensitive);
  if (firstPath == null) {
    return ParseResultNotFound();
  }

  final stages = <CommandStage>[];
  var idx = 0;

  while (idx < segments.length) {
    final seg = parseSegment(segments[idx]);
    final cmdPath =
        resolveCommand(seg.name, commandDirs, caseSensitive: caseSensitive);
    if (cmdPath == null) {
      if (stages.isEmpty) return ParseResultNotFound();
      break;
    }

    final meta = loadMetadata(root, seg.name);
    if (meta.invalid) {
      throw ParseError(
        'malformed metadata for command ${seg.name}: ${meta.malformedReason}',
        status: 500,
      );
    }

    if (meta.parseMode == 'raw') {
      if (idx != 0) {
        throw ParseError(
          'parse-mode raw on ${seg.name} is only valid in leftmost position',
          status: 500,
        );
      }
      final rawSuffix = _remainingRawSuffix(segments, idx + 1);
      final stage = CommandStage(
        name: seg.name,
        commandPath: cmdPath,
        argv: [],
        metadata: meta,
        stderrMergeBoundary: seg.stderrMerge,
        rawSegment: seg.raw,
      );
      return ParseResultRaw(RawCommandParse(stage: stage, rawSuffix: rawSuffix));
    }

    final queryArgv = coreArgvFromQuery(seg.queryItems);
    final argvFromQuery = queryArgv != null;
    List<String> argv;

    if (queryArgv != null) {
      argv = queryArgv;
      idx += 1;
    } else if (meta.arity == '*') {
      argv = segments
          .sublist(idx + 1)
          .map((s) => percentDecodeSegment(s, forFilesystem: false))
          .toList();
      idx = segments.length;
      stages.add(CommandStage(
        name: seg.name,
        commandPath: cmdPath,
        argv: argv,
        metadata: meta,
        stderrMergeBoundary: seg.stderrMerge,
        rawSegment: seg.raw,
        argvFromQuery: argvFromQuery,
      ));
      final pipeline = PipelineParse(
        stages: stages,
        inputSuffixRaw: null,
        pipelineDescription: formatPipeline(stages, null),
      );
      return ParseResultPipeline(pipeline);
    } else {
      final arity = (meta.arity is int) ? (meta.arity as int) : 0;
      if (arity > 0 && idx + arity >= segments.length) {
        throw ParseError(
          'command ${seg.name} expects arity $arity but insufficient path segments',
        );
      }
      argv = [];
      for (var offset = 1; offset <= arity; offset++) {
        final argSeg = parseSegment(segments[idx + offset]);
        if (argSeg.queryItems.any((item) => item.$1 == 'arg')) {
          if (resolveCommand(argSeg.name, commandDirs,
                  caseSensitive: caseSensitive) ==
              null) {
            throw ParseError(
                'core arg query on non-command segment ${argSeg.name}');
          }
        }
        argv.add(percentDecodeSegment(
            segments[idx + offset],
            forFilesystem: false));
      }
      idx += 1 + arity;
    }

    stages.add(CommandStage(
      name: seg.name,
      commandPath: cmdPath,
      argv: argv,
      metadata: meta,
      stderrMergeBoundary: seg.stderrMerge,
      rawSegment: seg.raw,
      argvFromQuery: argvFromQuery,
    ));

    if (idx >= segments.length) break;

    final nextSeg = parseSegment(segments[idx]);
    if (resolveCommand(nextSeg.name, commandDirs,
            caseSensitive: caseSensitive) !=
        null) {
      continue;
    }

    if (nextSeg.queryItems.any((item) => item.$1 == 'arg')) {
      throw ParseError('core arg query on non-command segment ${nextSeg.name}');
    }

    final remaining = segments.sublist(idx);
    for (final later in remaining.sublist(1)) {
      final laterSeg = parseSegment(later);
      if (resolveCommand(laterSeg.name, commandDirs,
              caseSensitive: caseSensitive) !=
          null) {
        throw ParseError(
          'unexpected segment ${nextSeg.name} before command ${laterSeg.name}',
        );
      }
      if (laterSeg.queryItems.any((item) => item.$1 == 'arg')) {
        throw ParseError(
            'core arg query on non-command segment ${laterSeg.name}');
      }
    }

    if (remaining.length > 1) {
      final lastStage = stages.last;
      if (!lastStage.argvFromQuery &&
          lastStage.metadata.arity == 0 &&
          lastStage.metadata.parseMode == 'normal') {
        throw ParseError(
          'metadata-free command ${lastStage.name} cannot consume path argument segments',
        );
      }
    }

    break;
  }

  List<String>? inputSuffix;
  if (idx < segments.length) {
    inputSuffix = segments.sublist(idx);
  }

  if (stages.isEmpty) return ParseResultNotFound();

  final pipeline = PipelineParse(
    stages: stages,
    inputSuffixRaw: inputSuffix,
    pipelineDescription: formatPipeline(stages, inputSuffix),
    sourcePath: inputSuffix != null ? inputSuffix.join('/') : null,
  );
  return ParseResultPipeline(pipeline);
}

void checkMethods(List<CommandStage> stages, String method) {
  final effective = (method == 'HEAD') ? 'GET' : method;
  for (final stage in stages) {
    if (stage.metadata.methods.isEmpty) {
      if (effective != 'GET') {
        throw ParseError(
          'method $method not permitted by command ${stage.name}',
          status: 405,
        );
      }
      continue;
    }
    if (!stage.metadata.methods.contains(effective)) {
      throw ParseError(
        'method $method not permitted by command ${stage.name}',
        status: 405,
      );
    }
  }
}
