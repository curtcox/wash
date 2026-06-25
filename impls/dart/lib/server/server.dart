import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../executor/executor.dart';
import '../filesystem/filesystem.dart';
import '../metadata/metadata.dart';
import '../parser/parser.dart';

const String _rawTargetHeader = 'x-wash-raw-target';

const int maxErrorBody = 8192;

class ServerConfig {
  final String root;
  final List<String> commandDirs;
  final ExecConfig execConfig;

  ServerConfig({
    required this.root,
    required this.commandDirs,
    required this.execConfig,
  });

  factory ServerConfig.fromRoot(String rootPath) {
    final resolved = Directory(rootPath).resolveSymbolicLinksSync();
    final commandDirs = loadCommandPath(resolved);
    final execConfig = loadExecRules(resolved);
    return ServerConfig(
      root: resolved,
      commandDirs: commandDirs,
      execConfig: execConfig,
    );
  }
}

class WashServer {
  final HttpServer _server;
  final RawServerSocket _rawSocket;
  final ServerConfig _config;

  WashServer._(this._server, this._rawSocket, this._config);

  static Future<WashServer> bind(
    String host,
    int port,
    ServerConfig config,
  ) async {
    final rawSocket = await RawServerSocket.bind(host, port);
    final server = await HttpServer.listenOn(_PatchedServerSocket(rawSocket));
    return WashServer._(server, rawSocket, config);
  }

  int get port => _rawSocket.port;

  Future<void> serve() async {
    await for (final request in _server) {
      unawaited(_handleRequest(request));
    }
  }

  Future<void> close() async {
    await _server.close();
    await _rawSocket.close();
  }

  Future<void> _handleRequest(HttpRequest request) async {
    try {
      await _dispatch(request);
    } catch (e) {
      try {
        await _sendError(request.response, 500, 'internal server error');
      } catch (_) {}
    }
  }

  String _rawTarget(HttpRequest request) {
    // Recover the raw request-target injected by _PatchedServerSocket
    final injected = request.headers.value(_rawTargetHeader);
    if (injected != null && injected.isNotEmpty) return injected;
    // Fallback: use request.uri (may be normalized by Dart's HTTP parser)
    var target = request.uri.toString();
    if (!target.startsWith('/')) target = '/$target';
    return target.split('#')[0];
  }

  Future<List<int>> _requestBody(HttpRequest request) async {
    final contentLength = request.contentLength;
    if (contentLength == 0) return [];
    final chunks = <int>[];
    await for (final chunk in request) {
      chunks.addAll(chunk);
    }
    return chunks;
  }

  bool _acceptsJson(HttpRequest request) {
    final accept = request.headers.value('accept') ?? '';
    final parts = accept.split(',');
    if (parts.isEmpty) return false;
    final first = parts[0].trim().toLowerCase();
    return accept.contains('application/json') &&
        !first.startsWith('text/plain');
  }

  List<int> _errorBody(
    HttpRequest request,
    int status,
    String message, {
    Map<String, dynamic>? extra,
  }) {
    extra ??= {};
    List<int> body;
    if (_acceptsJson(request)) {
      final payload = {'status': status, 'error': message, ...extra};
      body = utf8.encode(jsonEncode(payload));
    } else {
      final lines = [message];
      for (final entry in extra.entries) {
        lines.add('${entry.key}: ${entry.value}');
      }
      var text = lines.join('\n');
      if (!text.endsWith('\n')) text += '\n';
      body = utf8.encode(text);
    }
    if (body.length > maxErrorBody) {
      final truncated = body.sublist(0, maxErrorBody - 32);
      final suffix = utf8.encode('\n... [truncated]\n');
      body = [...truncated, ...suffix];
    }
    return body;
  }

  Future<void> _sendResponse(
    HttpResponse response,
    int status,
    List<int> body, {
    String contentType = 'text/plain',
    Map<String, String>? extraHeaders,
    bool omitBody = false,
  }) async {
    response.statusCode = status;
    response.headers.set('content-type', contentType);
    response.headers.set('content-length', omitBody ? '0' : '${body.length}');
    if (extraHeaders != null) {
      for (final entry in extraHeaders.entries) {
        response.headers.set(entry.key, entry.value);
      }
    }
    if (!omitBody) {
      response.add(body);
    }
    await response.close();
  }

  Future<void> _sendError(
    HttpResponse response,
    int status,
    String message, {
    Map<String, dynamic>? extra,
    HttpRequest? request,
  }) async {
    // When request is null we can't content-negotiate; use plain text
    List<int> body;
    if (request != null) {
      body = _errorBody(request, status, message, extra: extra);
    } else {
      var text = message;
      if (!text.endsWith('\n')) text += '\n';
      body = utf8.encode(text);
    }
    response.statusCode = status;
    response.headers.set('content-type', 'text/plain; charset=utf-8');
    response.headers.set('content-length', '${body.length}');
    response.add(body);
    await response.close();
  }

  Future<void> _sendErrorReq(
    HttpRequest request,
    int status,
    String message, {
    Map<String, dynamic>? extra,
  }) async {
    final body = _errorBody(request, status, message, extra: extra);
    final contentType = _acceptsJson(request)
        ? 'application/json; charset=utf-8'
        : 'text/plain; charset=utf-8';
    await _sendResponse(
      request.response,
      status,
      body,
      contentType: contentType,
    );
  }

  Map<String, String> _pipelineHeaders(PipelineResult result) {
    final headers = <String, String>{};
    if (result.finalCommand != null) {
      headers['x-webshell-command'] = result.finalCommand!;
    }
    if (result.pipelineDescription.isNotEmpty) {
      headers['x-webshell-pipeline'] = result.pipelineDescription;
    }
    if (result.sourcePath != null) {
      headers['x-webshell-source'] =
          '${_config.root}${Platform.pathSeparator}${result.sourcePath}';
    }
    return headers;
  }

  Future<void> _handleFilesystemGet(
    HttpRequest request,
    FilesystemResource resource,
  ) async {
    final omitBody = request.method == 'HEAD';
    final extraHeaders = resource.viaIndirection
        ? <String, String>{'X-WebShell-Resolved-Path': resource.path}
        : null;
    try {
      if (resource.kind == ResourceKind.file) {
        final data = readFileBytes(resource.path);
        await _sendResponse(
          request.response,
          200,
          data,
          contentType: inferMime(resource.path, root: _config.root),
          extraHeaders: extraHeaders,
          omitBody: omitBody,
        );
        return;
      }

      final index = findIndexFile(resource.path, loadIndexNames(_config.root));
      if (index != null) {
        final data = readFileBytes(index);
        await _sendResponse(
          request.response,
          200,
          data,
          contentType: inferMime(index, root: _config.root),
          extraHeaders: extraHeaders,
          omitBody: omitBody,
        );
        return;
      }

      if (!listingEnabled(_config.root)) {
        await _sendErrorReq(request, 404, 'not found');
        return;
      }
    } on EnvConfigError catch (e) {
      await _sendErrorReq(request, 500, e.message);
      return;
    }

    final listing = directoryListing(resource.path);
    await _sendResponse(
      request.response,
      200,
      listing,
      contentType: 'text/plain; charset=utf-8',
      extraHeaders: extraHeaders,
      omitBody: omitBody,
    );
  }

  Future<void> _handlePutDeleteLiteral(
    HttpRequest request,
    String method,
    String rawTarget,
  ) async {
    final pathPart = rawTarget.split('?')[0];
    final segments = splitRawTarget(pathPart);
    List<String> parts;
    try {
      parts = literalPathPartsFromRaw(segments);
    } catch (e) {
      await _sendErrorReq(request, 400, 'invalid path');
      return;
    }

    if (method == 'PUT') {
      final body = await _requestBody(request);
      try {
        final resolved = resolveUnderRoot(_config.root, parts);
        if (resolved != null) {
          final stat = FileStat.statSync(resolved);
          if (stat.type != FileSystemEntityType.directory) {
            final normalized = normalizePathParts(parts);
            var literalTarget = _config.root;
            for (final part in normalized) {
              literalTarget = '$literalTarget${Platform.pathSeparator}$part';
            }
            var resolvedLiteral = literalTarget;
            try {
              resolvedLiteral = File(literalTarget).resolveSymbolicLinksSync();
            } catch (_) {
              try {
                resolvedLiteral =
                    Directory(literalTarget).resolveSymbolicLinksSync();
              } catch (_) {}
            }
            if (File(resolved).absolute.path !=
                File(resolvedLiteral).absolute.path) {
              File(resolved).writeAsBytesSync(body);
              await _sendResponse(
                request.response,
                200,
                [],
                contentType: 'text/plain; charset=utf-8',
              );
              return;
            }
          }
        }
        putFile(_config.root, parts, body, createParents: true);
      } on RootEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on SymlinkEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on NameEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on NameLoopError {
        await _sendErrorReq(request, 508, 'name resolution loop detected');
        return;
      } on FileSystemException catch (e) {
        final msg = e.message.toLowerCase();
        if (msg.contains('parent')) {
          await _sendErrorReq(request, 404, 'parent directory not found');
        } else {
          await _sendErrorReq(request, 500, 'write failed: ${e.message}');
        }
        return;
      } catch (e) {
        await _sendErrorReq(request, 500, 'write failed: $e');
        return;
      }
      await _sendResponse(
        request.response,
        200,
        [],
        contentType: 'text/plain; charset=utf-8',
      );
      return;
    }

    if (method == 'DELETE') {
      try {
        deleteFile(_config.root, parts);
      } on RootEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on SymlinkEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on NameEscapeError {
        await _sendErrorReq(request, 403, 'path not permitted');
        return;
      } on NameLoopError {
        await _sendErrorReq(request, 508, 'name resolution loop detected');
        return;
      } on FileSystemException catch (e) {
        final msg = e.message.toLowerCase();
        if (msg.contains('not found') || msg.contains('no such')) {
          await _sendErrorReq(request, 404, 'file not found');
        } else {
          await _sendErrorReq(request, 500, 'delete failed: ${e.message}');
        }
        return;
      } catch (e) {
        await _sendErrorReq(request, 500, 'delete failed: $e');
        return;
      }
      await _sendResponse(
        request.response,
        200,
        [],
        contentType: 'text/plain; charset=utf-8',
      );
      return;
    }
  }

  Future<void> _handleCommand(
    HttpRequest request,
    ParseResult parsed, {
    required List<int> body,
  }) async {
    final method = request.method;

    // For HEAD: check methods first, then execute as GET
    if (method == 'HEAD') {
      if (parsed is ParseResultPipeline) {
        try {
          checkMethods(parsed.pipeline.stages, method);
        } on ParseError catch (e) {
          await _sendErrorReq(request, e.status, e.message);
          return;
        }
      } else if (parsed is ParseResultRaw) {
        try {
          checkMethods([parsed.raw.stage], method);
        } on ParseError catch (e) {
          await _sendErrorReq(request, e.status, e.message);
          return;
        }
      }
    }

    PipelineResult result;
    try {
      if (parsed is ParseResultRaw) {
        final effectiveMethod = (method == 'HEAD') ? 'GET' : method;
        try {
          checkMethods([parsed.raw.stage], request.method);
        } on ParseError catch (e) {
          await _sendErrorReq(request, e.status, e.message);
          return;
        }
        result = await executeRawCommand(
          parsed.raw,
          root: _config.root,
          commandDirs: _config.commandDirs,
          execConfig: _config.execConfig,
          method: effectiveMethod,
          body: body,
        );
      } else if (parsed is ParseResultPipeline) {
        try {
          checkMethods(parsed.pipeline.stages, request.method);
        } on ParseError catch (e) {
          await _sendErrorReq(request, e.status, e.message);
          return;
        }
        result = await executePipeline(
          parsed.pipeline,
          root: _config.root,
          commandDirs: _config.commandDirs,
          execConfig: _config.execConfig,
          body: body,
        );
      } else {
        await _sendErrorReq(request, 500, 'unexpected parse result type');
        return;
      }
    } on ParseError catch (e) {
      await _sendErrorReq(request, e.status, e.message);
      return;
    } on ExecutionError catch (e) {
      await _sendErrorReq(request, e.status, e.message);
      return;
    }

    if (result.httpStatus >= 400) {
      final fail = result.failingStage;
      final extra = <String, dynamic>{'pipeline': result.pipelineDescription};
      if (fail != null) {
        extra['command'] = fail.name;
        extra['exit_status'] = fail.exitCode;
        if (fail.stdout.isNotEmpty) {
          extra['stdout'] =
              utf8.decode(fail.stdout, allowMalformed: true).substring(
                    0,
                    fail.stdout.length > 8192 ? 8192 : fail.stdout.length,
                  );
        }
        if (fail.stderr.isNotEmpty) {
          extra['stderr'] =
              utf8.decode(fail.stderr, allowMalformed: true).substring(
                    0,
                    fail.stderr.length > 8192 ? 8192 : fail.stderr.length,
                  );
        }
      }
      await _sendErrorReq(
        request,
        result.httpStatus,
        'command failed',
        extra: extra,
      );
      return;
    }

    final omitBody = method == 'HEAD';
    if (method == 'HEAD') {
      if (parsed is ParseResultPipeline) {
        if (!parsed.pipeline.stages.every((s) => headPermitted(s.metadata))) {
          await _sendErrorReq(request, 405, 'method HEAD not permitted');
          return;
        }
      } else if (parsed is ParseResultRaw) {
        if (!headPermitted(parsed.raw.stage.metadata)) {
          await _sendErrorReq(request, 405, 'method HEAD not permitted');
          return;
        }
      }
    }

    final contentType = inferMimeFromBytes(result.stdout, result.contentType);
    await _sendResponse(
      request.response,
      200,
      result.stdout,
      contentType: contentType,
      extraHeaders: _pipelineHeaders(result),
      omitBody: omitBody,
    );
  }

  Future<void> _dispatch(HttpRequest request) async {
    final rawTarget = _rawTarget(request);
    final method = request.method;

    if (method == 'OPTIONS') {
      request.response.statusCode = 204;
      request.response.headers.set('content-length', '0');
      await request.response.close();
      return;
    }

    if (method == 'PUT' || method == 'DELETE') {
      await _handlePutDeleteLiteral(request, method, rawTarget);
      return;
    }

    final List<int> body;
    if (method == 'POST' || method == 'PATCH') {
      body = await _requestBody(request);
    } else {
      body = [];
    }

    ParseResult parsed;
    try {
      parsed = parseRequest(
        method,
        rawTarget,
        _config.root,
        commandDirs: _config.commandDirs,
      );
    } on ParseError catch (e) {
      await _sendErrorReq(request, e.status, e.message);
      return;
    }

    if (parsed is ParseResultFilesystem) {
      if (method == 'GET' || method == 'HEAD') {
        await _handleFilesystemGet(request, parsed.resource);
        return;
      }
      if (method == 'POST') {
        await _sendErrorReq(
          request,
          405,
          'POST not permitted for plain file resource',
        );
        return;
      }
      await _sendErrorReq(request, 405, 'method $method not permitted');
      return;
    }

    if (parsed is ParseResultNotFound) {
      await _sendErrorReq(request, 404, 'not found');
      return;
    }

    if (method == 'POST' && parsed is ParseResultPipeline) {
      for (final stage in parsed.pipeline.stages) {
        if (!stage.metadata.methods.contains('POST')) {
          await _sendErrorReq(
            request,
            405,
            'method POST not permitted by command ${stage.name}',
          );
          return;
        }
      }
    }

    await _handleCommand(request, parsed, body: body);
  }
}

Future<(WashServer, int)> createServer(
  String root,
  String host,
  int port,
) async {
  final config = ServerConfig.fromRoot(root);
  final server = await WashServer.bind(host, port, config);
  return (server, server.port);
}

// ---------------------------------------------------------------------------
// Raw-socket middleware: sniff request line, inject raw target as header
// ---------------------------------------------------------------------------

class _PatchedServerSocket extends Stream<Socket> implements ServerSocket {
  final RawServerSocket _raw;

  _PatchedServerSocket(this._raw);

  @override
  InternetAddress get address => _raw.address;

  @override
  int get port => _raw.port;

  @override
  Future<ServerSocket> close() async {
    await _raw.close();
    return this;
  }

  @override
  StreamSubscription<Socket> listen(
    void Function(Socket event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return _raw.map(_PatchedSocket.new).listen(
          onData,
          onError: onError,
          onDone: onDone,
          cancelOnError: cancelOnError,
        );
  }
}

/// Wraps a [RawSocket] as a [Socket] and rewrites the first HTTP request line
/// to inject the raw request-target as an extra header before the HTTP parser
/// sees it.  This lets us preserve `..` and `%2e%2e` path segments that
/// Dart's built-in URI normalisation would otherwise collapse.
class _PatchedSocket extends Stream<Uint8List> implements Socket {
  final RawSocket _raw;

  // Buffered bytes coming FROM the network (client → server).
  final _inbuf = BytesBuilder(copy: false);
  bool _headerInjected = false;
  bool _closed = false;

  // Controller that feeds the patched byte stream to HttpServer.
  final _ctrl = StreamController<Uint8List>(sync: true);

  _PatchedSocket(this._raw) {
    _raw.readEventsEnabled = true;
    _raw.listen(_onRawEvent, onError: _ctrl.addError, onDone: _ctrl.close);
  }

  // ---- Stream<Uint8List> --------------------------------------------------

  @override
  StreamSubscription<Uint8List> listen(
    void Function(Uint8List event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) =>
      _ctrl.stream.listen(
        onData,
        onError: onError,
        onDone: onDone,
        cancelOnError: cancelOnError,
      );

  // ---- IOSink (writes from server → client) --------------------------------

  @override
  Encoding get encoding => utf8;

  @override
  set encoding(Encoding value) {}

  @override
  void add(List<int> data) {
    if (!_closed) _raw.write(data);
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future addStream(Stream<List<int>> stream) async {
    await for (final chunk in stream) {
      add(chunk);
    }
  }

  @override
  Future flush() async {}

  @override
  Future close() async {
    _closed = true;
    _raw.shutdown(SocketDirection.send);
  }

  @override
  Future get done => _ctrl.done;

  @override
  void write(Object? object) => add(utf8.encode('$object'));

  @override
  void writeAll(Iterable objects, [String separator = '']) =>
      write(objects.join(separator));

  @override
  void writeCharCode(int charCode) => add([charCode]);

  @override
  void writeln([Object? object = '']) => write('$object\n');

  // ---- Socket metadata ----------------------------------------------------

  @override
  InternetAddress get address => _raw.address;

  @override
  InternetAddress get remoteAddress => _raw.remoteAddress;

  @override
  int get port => _raw.port;

  @override
  int get remotePort => _raw.remotePort;

  @override
  bool setOption(SocketOption option, bool enabled) =>
      _raw.setOption(option, enabled);

  @override
  Uint8List getRawOption(RawSocketOption option) => _raw.getRawOption(option);

  @override
  void setRawOption(RawSocketOption option) => _raw.setRawOption(option);

  @override
  void destroy() {
    _closed = true;
    _raw.close();
  }

  // ---- Internal -----------------------------------------------------------

  void _onRawEvent(RawSocketEvent event) {
    if (event == RawSocketEvent.read) {
      final data = _raw.read();
      if (data == null || data.isEmpty) return;
      if (_headerInjected) {
        _ctrl.add(data);
        return;
      }
      _inbuf.add(data);
      final bytes = _inbuf.toBytes();
      // Look for \r\n ending the request line
      final crlfIdx = _findCRLF(bytes);
      if (crlfIdx < 0) return; // need more data

      // We have at least one complete line.
      _headerInjected = true;
      final requestLine = latin1.decode(bytes.sublist(0, crlfIdx));
      final rawTarget = _extractTarget(requestLine);

      // Re-emit bytes with the extra header injected after the request line.
      if (rawTarget != null) {
        final injected = '$_rawTargetHeader: $rawTarget\r\n'.codeUnits;
        final before = bytes.sublist(0, crlfIdx + 2); // include \r\n
        final after = bytes.sublist(crlfIdx + 2);
        _ctrl.add(Uint8List.fromList([...before, ...injected, ...after]));
      } else {
        _ctrl.add(bytes);
      }
      _inbuf.clear();
    } else if (event == RawSocketEvent.readClosed ||
        event == RawSocketEvent.closed) {
      if (!_headerInjected && _inbuf.length > 0) {
        _ctrl.add(_inbuf.toBytes());
      }
      _ctrl.close();
    }
  }

  static int _findCRLF(Uint8List bytes) {
    for (var i = 0; i < bytes.length - 1; i++) {
      if (bytes[i] == 0x0d && bytes[i + 1] == 0x0a) return i;
    }
    return -1;
  }

  static String? _extractTarget(String requestLine) {
    final parts = requestLine.split(' ');
    if (parts.length < 2) return null;
    var target = parts[1];
    // Strip fragment
    final hashIdx = target.indexOf('#');
    if (hashIdx >= 0) target = target.substring(0, hashIdx);
    return target;
  }
}
