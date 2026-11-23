<?php
// Backend for the WebXR STL/OBJ inspector on ordinary PHP hosting (Apache / Nginx + PHP).
// Stores models in the same folder as index.html. Same API as server.py:
//   GET  api.php?action=list
//   POST api.php?action=upload&name=file.stl   (raw file bytes as request body)
//   POST api.php?action=delete&name=file.stl
// For big files raise post_max_size / upload_max_filesize in php.ini, and make the folder writable.

header('Cache-Control: no-store');
$dir = __DIR__;

function out($code, $data) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data);
    exit;
}

function safe_name($raw) {
    $n = basename(str_replace('\\', '/', (string)$raw));
    $clean = @preg_replace('/[^\p{L}\p{N}_.\- ()]+/u', '_', $n);
    if ($clean === null) $clean = preg_replace('/[^A-Za-z0-9_.\- ()]+/', '_', $n);
    $clean = trim($clean, ' .');
    $ext = strtolower(pathinfo($clean, PATHINFO_EXTENSION));
    $stem = pathinfo($clean, PATHINFO_FILENAME);
    if ($stem === '' || !in_array($ext, ['stl', 'obj'], true)) return null;
    return mb_substr($stem, 0, 150) . '.' . $ext;
}

$action = $_GET['action'] ?? 'list';

if ($action === 'list') {
    $files = [];
    foreach (scandir($dir) as $f) {
        $p = "$dir/$f";
        if (is_file($p) && in_array(strtolower(pathinfo($f, PATHINFO_EXTENSION)), ['stl', 'obj'], true)) {
            $files[] = ['name' => $f, 'size' => filesize($p), 'mtime' => filemtime($p)];
        }
    }
    usort($files, fn($a, $b) => $b['mtime'] <=> $a['mtime']);
    out(200, ['ok' => true, 'files' => $files]);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') out(405, ['ok' => false, 'error' => 'use POST']);
$name = safe_name($_GET['name'] ?? '');
if (!$name) out(400, ['ok' => false, 'error' => 'only .stl and .obj files are allowed']);

if ($action === 'upload') {
    $stem = pathinfo($name, PATHINFO_FILENAME); $ext = pathinfo($name, PATHINFO_EXTENSION);
    $target = "$dir/$name"; $i = 1;
    while (file_exists($target)) $target = "$dir/{$stem}_" . $i++ . ".$ext";
    $tmp = tempnam($dir, '.upload-');
    $in = fopen('php://input', 'rb'); $o = fopen($tmp, 'wb');
    $bytes = stream_copy_to_stream($in, $o);
    fclose($in); fclose($o);
    if (!$bytes) { @unlink($tmp); out(400, ['ok' => false, 'error' => 'empty upload (file larger than post_max_size?)']); }
    if (!rename($tmp, $target)) { @unlink($tmp); out(500, ['ok' => false, 'error' => 'could not save file (folder writable?)']); }
    @chmod($target, 0644);
    out(200, ['ok' => true, 'name' => basename($target)]);
}

if ($action === 'delete') {
    $p = "$dir/$name";
    if (!is_file($p)) out(404, ['ok' => false, 'error' => 'no such file']);
    if (!unlink($p)) out(500, ['ok' => false, 'error' => 'could not delete']);
    out(200, ['ok' => true, 'name' => $name]);
}

out(400, ['ok' => false, 'error' => 'unknown action']);
