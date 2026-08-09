# Round 13 - V3 Win32 Relative-Open ABI Acceptance V0 (Proposed, Non-Authoritative)

Status: PROPOSED

Review: AWAIT_INDEPENDENT_REVIEW

Authorization: NOT_GO_RUN

Implementation: STOP_IMPLEMENTATION

> **Non-authoritative, design-only.** This document is a working proposal: it
> is design-only, it is **not** in a formal artifact allowlist, and it creates
> - and must not be read as creating - any approval, claim, attempt,
> consumption, run, or data access. Nothing in this document authorizes a run,
> and no parseable GO/envelope/claim instance is produced anywhere in this
> document. **Implementation stops**: this proposal pins an ABI for review only
> and carries the `STOP_IMPLEMENTATION` marker.

---

## 1. Scope and hard rejections

**Frozen platform scope:** Windows native x64, local fixed NTFS/ReFS volume
directories only. Acceptance requires all of the following: pointer size is 8;
`IsWow64Process2` returns `process_machine == IMAGE_FILE_MACHINE_UNKNOWN (0)`
and `native_machine == IMAGE_FILE_MACHINE_AMD64 (0x8664)`;
`GetDriveTypeW(root) == DRIVE_FIXED (3)`; `GetFinalPathNameByHandleW` with
`FILE_NAME_NORMALIZED (0)` and `VOLUME_NAME_GUID (1)` returns exactly a volume
GUID root with no suffix; and `GetVolumeInformationByHandleW` reports filesystem
name `NTFS` or `ReFS` (case-insensitive). Any failed API call or predicate is a
closed scope failure. This rejects remote or mapped drives, SUBST roots, device
subpaths, non-root handles, unsupported filesystems, and WOW64.

**Hard rejections (never downgraded, never fallback):**

- **UNC** paths (`\\server\share`, `\\?\UNC\...`).
- **Mapped** network drives.
- **Drive letters routed to remote/network** (not `DRIVE_FIXED`).
- **SUBST** and any other DOS device/alias virtualization.
- **Device paths** (`\\.\`, `\Device\...`, `\??\`, `\\?\Volume{...}` beyond the
  local root).
- **WOW64** mismatch (pointer size != 8, or `IsWow64Process2` reporting a
  non-native process architecture / redirected resolution).

Every rejection surfaces a **fixed closed enum** (sect. 8) with no
path/status/exception leakage.

## 2. Bootstrap: CreateFileW, volume root only

The **only** `CreateFileW` call is the volume root bootstrap:

```c
HANDLE hRoot = CreateFileW(
    L"\\\\?\\C:\\",           /* verified local fixed X:\ root */
    FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
    FILE_SHARE_READ | FILE_SHARE_WRITE,   /* no DELETE */
    NULL, OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
```

`FILE_TRAVERSE` = `0x20`. Share is read|write, **no `FILE_SHARE_DELETE`**.
After the root handle is held, **every** descendant is opened via
`ntdll!NtCreateFile` using `OBJECT_ATTRIBUTES.RootDirectory` bound to a held
ancestor handle. Sizes/flags of share and disposition are given in sect. 5.

## 3. NtCreateFile exact ABI and structs (Windows x64, ctypes)

`NtCreateFile` is resolved from `ntdll.dll` by the exported name
`NtCreateFile`; ordinal/index binding is forbidden. Its signature is:

```c
NTSTATUS NtCreateFile(
  PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES, PIO_STATUS_BLOCK,
  PLARGE_INTEGER AllocationSize /* NULL */, ULONG FileAttributes,
  ULONG ShareAccess, ULONG CreateDisposition, ULONG CreateOptions,
  PVOID EaBuffer /* NULL */, ULONG EaLength /* 0 */);
```

**Pinned struct sizes/offsets** (ctypes `_pack_` 0, natural alignment; exact):

- **UNICODE_STRING = 16 bytes**: `c_ushort Length` (0), `c_ushort MaximumLength`
  (2), pad (4-7), `c_void_p Buffer` (8).
- **OBJECT_ATTRIBUTES = 48 bytes**: `c_ulong Length` (0, must equal 48), pad
  (4-7), `c_void_p RootDirectory` (8), `POINTER(UNICODE_STRING) ObjectName`
  (16), `c_ulong Attributes` (24, pad 28-31), `c_void_p SecurityDescriptor`
  (32), `c_void_p SecurityQualityOfService` (40).
- **IO_STATUS_BLOCK = 16 bytes**: a real ctypes `Union` at offset 0 with
  `Status: c_long` and `Pointer: c_void_p`, embedded in a `Structure` followed
  by `Information: c_size_t` at offset 8.
- **FILE_STANDARD_INFO = 24 bytes** (`FileStandardInfo` = 1):
  `c_longlong AllocationSize` (0), `c_longlong EndOfFile` (8),
  `c_ulong NumberOfLinks` (16), `c_ubyte DeletePending` (20), `c_ubyte Directory`
  (21), pad (22-23).
- **FILE_ATTRIBUTE_TAG_INFO = 8 bytes** (`FileAttributeTagInfo` = 9):
  `c_ulong FileAttributes` (0), `c_ulong ReparseTag` (4).
- **FILE_ID_INFO = 24 bytes** (`FileIdInfo` = 18): `c_ulonglong
  VolumeSerialNumber` (0), `c_ulonglong FileId.Identifier[0]` (8),
  `c_ulonglong FileId.Identifier[1]` (16).

The required union layout is literal, not a pointer placeholder:

```python
class IO_STATUS_VALUE(ctypes.Union):
    _fields_ = [("Status", ctypes.c_long), ("Pointer", ctypes.c_void_p)]

class IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [("Value", IO_STATUS_VALUE),
                ("Information", ctypes.c_size_t)]
```

Pinned scalar aliases are `HANDLE/PVOID=c_void_p`, `DWORD/ULONG/ACCESS_MASK=
c_uint32`, `ULONG_PTR=c_size_t`, `USHORT=c_ushort`, `BOOLEAN=c_ubyte`,
`BOOL=c_int`, and `NTSTATUS=c_long`. Exact ctypes `argtypes -> restype` are:

- `CreateFileW(c_wchar_p,DWORD,DWORD,c_void_p,DWORD,DWORD,HANDLE) -> HANDLE`.
- `NtCreateFile(POINTER(HANDLE),ACCESS_MASK,POINTER(OBJECT_ATTRIBUTES),
  POINTER(IO_STATUS_BLOCK),POINTER(c_longlong),ULONG,ULONG,ULONG,ULONG,PVOID,
  ULONG) -> NTSTATUS`.
- `NtQueryDirectoryFile(HANDLE,HANDLE,PVOID,PVOID,POINTER(IO_STATUS_BLOCK),
  PVOID,ULONG,c_int,BOOLEAN,POINTER(UNICODE_STRING),BOOLEAN) -> NTSTATUS`.
- `GetFileInformationByHandleEx(HANDLE,c_int,PVOID,DWORD) -> BOOL`.
- `WriteFile(HANDLE,PVOID,DWORD,POINTER(DWORD),PVOID) -> BOOL` and the same
  shape for `ReadFile`.
- `FlushFileBuffers(HANDLE) -> BOOL`.
- `SetFilePointerEx(HANDLE,c_longlong,POINTER(c_longlong),DWORD) -> BOOL`.
- `CloseHandle(HANDLE) -> BOOL`.
- `GetDriveTypeW(c_wchar_p) -> DWORD`.
- `GetFinalPathNameByHandleW(HANDLE,POINTER(c_wchar),DWORD,DWORD) -> DWORD`.
- `IsWow64Process2(HANDLE,POINTER(USHORT),POINTER(USHORT)) -> BOOL`.
- `GetVolumeInformationByHandleW(HANDLE,POINTER(c_wchar),DWORD,
  POINTER(DWORD),POINTER(DWORD),POINTER(DWORD),POINTER(c_wchar),DWORD) -> BOOL`.
- `GetCurrentProcess() -> HANDLE` and `GetLastError() -> DWORD`.
- `RtlNtStatusToDosError(NTSTATUS) -> DWORD`, diagnostic-only and never used
  to select an external enum.

Every BOOL failure is detected immediately and its `GetLastError` value remains
internal. Buffer sizes passed to `GetFileInformationByHandleEx` must exactly
match the pinned structure size.

## 4. Relative component rules

- **One UTF-16 component only**: no `\`, `/`, `:`, NUL, ADS, empty component,
  or `.`/`..`. `UNICODE_STRING.Length` is the UTF-16 byte length excluding NUL;
  `MaximumLength` includes the terminating NUL, and the backing buffer remains
  alive through the complete native call. Both lengths must fit `USHORT`
  without truncation, `MaximumLength == Length + 2`, and the UTF-16 code-unit
  count must not exceed the maximum component length returned by
  `GetVolumeInformationByHandleW`. Encoding failure or overflow is rejected
  before `NtCreateFile`.
- Pinned `OBJECT_ATTRIBUTES.Attributes`: `OBJ_CASE_INSENSITIVE` (0x40) and
  `OBJ_DONT_REPARSE` (0x1000) always set; `OBJ_KERNEL_HANDLE`,
  `OBJ_PERMANENT`, `OBJ_INHERIT`, `OBJ_OPENIF` never set.
- No string path reopen ever after the root handle.

## 5. Pinned access/share/disposition/options

| Symbol | Value |
|---|---|
| FILE_LIST_DIRECTORY | 0x1 |
| FILE_TRAVERSE | 0x20 |
| FILE_ADD_FILE | 0x2 |
| FILE_READ_ATTRIBUTES | 0x80 |
| SYNCHRONIZE | 0x100000 |
| FILE_READ_DATA | 0x1 |
| FILE_WRITE_DATA | 0x2 |
| FILE_SHARE_READ / _WRITE / _DELETE | 0x1 / 0x2 / 0x4 |
| FILE_OPEN (disposition) | 0x1 |
| FILE_CREATE (CreateDisposition) | 0x2 |
| FILE_ADD_FILE (directory DesiredAccess) | 0x2 |
| FILE_DIRECTORY_FILE | 0x1 |
| FILE_SYNCHRONOUS_IO_NONALERT | 0x20 |
| FILE_NON_DIRECTORY_FILE | 0x40 |
| FILE_WRITE_THROUGH | 0x2 |
| FILE_OPEN_REPARSE_POINT | 0x200000 |
| FILE_ATTRIBUTE_NORMAL | 0x80 |
| OPEN_EXISTING | 3 |
| FILE_FLAG_BACKUP_SEMANTICS | 0x02000000 |
| FILE_FLAG_OPEN_REPARSE_POINT | 0x00200000 |
| FILE_ATTRIBUTE_DIRECTORY | 0x10 |
| FILE_ATTRIBUTE_REPARSE_POINT | 0x400 |
| FILE_BEGIN | 0 |

**Roles:**

- **Volume root** (`CreateFileW`): access `FILE_LIST_DIRECTORY|FILE_TRAVERSE|
  FILE_READ_ATTRIBUTES|SYNCHRONIZE`; share `FILE_SHARE_READ|FILE_SHARE_WRITE`
  (no delete); `OPEN_EXISTING`; flags `BACKUP_SEMANTICS|OPEN_REPARSE_POINT`.
- **Directories** (relative `NtCreateFile`): access `FILE_LIST_DIRECTORY|
  FILE_TRAVERSE|FILE_READ_ATTRIBUTES|SYNCHRONIZE`; share
  `FILE_SHARE_READ|FILE_SHARE_WRITE`; disposition `FILE_OPEN`; options
  `FILE_DIRECTORY_FILE|FILE_SYNCHRONOUS_IO_NONALERT|FILE_OPEN_REPARSE_POINT`.
  Directory validity additionally carries **`FILE_ADD_FILE`** access (proving
  the parent can add files) while still requiring `FILE_LIST_DIRECTORY`.
  Success requires `NT_SUCCESS(status)`, a valid HANDLE, and
  `IO_STATUS_BLOCK.Information == FILE_OPENED (1)`.
- **Claim / relative file create** (`FILE_CREATE`): `FileAttributes =
  FILE_ATTRIBUTE_NORMAL (0x80)`; access `FILE_READ_DATA|FILE_WRITE_DATA|
  FILE_READ_ATTRIBUTES|SYNCHRONIZE`; share **`FILE_SHARE_READ` only**;
  options `FILE_WRITE_THROUGH|FILE_SYNCHRONOUS_IO_NONALERT|FILE_NON_DIRECTORY_FILE|
  FILE_OPEN_REPARSE_POINT`.
  Success requires `NT_SUCCESS(status)`, a valid HANDLE, and
  `IO_STATUS_BLOCK.Information == FILE_CREATED (2)`; `FILE_OPEN_IF` is never an
  acceptable substitute.

**Forbidden** on the relative file create and throughout: `FILE_OPEN_IF`,
`FILE_OVERWRITE_IF`, `DELETE` access, `FILE_APPEND_DATA`, `FILE_WRITE_ATTRIBUTES`.
These are hard-fail if requested/observed.

**Reparse:** a non-zero `ReparseTag` (or any `FILE_ATTRIBUTE_REPARSE_POINT`
attribute) on **any** handle is a hard failure. Middle-path components use
`OBJ_DONT_REPARSE`; no reparse target is ever accepted at any handle, leaf or
otherwise.

## 6. Handle-only identity and enumeration

- All metadata is queried from the same HANDLE with
  `GetFileInformationByHandleEx`: `FileIdInfo=18` with a 24-byte buffer,
  `FileAttributeTagInfo=9` with an 8-byte buffer, and `FileStandardInfo=1`
  with a 24-byte buffer. A false BOOL is a closed failure. Volume serial must
  equal the root's, `DeletePending=0`, and `Directory` must match the role.
  Every directory has `NumberOfLinks > 0`, stable at each lease boundary; every
  regular formal leaf has `NumberOfLinks == 1`.
- **`IO_STATUS_BLOCK`** is a **real union**: set `Status` (NTSTATUS or Pointer)
  plus `Information`; the identical 16-byte struct is used by both
  `NtCreateFile` and `NtQueryDirectoryFile`.

**Preclaim presence** is proven **handle-relative**, never by walking absolute
paths. Before mutation, enumerate and probe the complete fixed closure: every
V3 claim/results/verdict/index name, every V1/V2 formal name, and every
candidate/staging/temp pattern fixed by the protocol. If the read-only probe
finds any reserved name, refuse preclaim and do not call `FILE_CREATE`. If the
probe reports absent but a concurrent actor creates the claim before mutation,
the attempted `FILE_CREATE` returns the fixed collision status and never
overwrites. These are distinct tested paths.

## 7. Enumeration and write/read lifecycle

**`NtQueryDirectoryFile`** uses the exact prototype in sect. 3 and native
`FileNamesInformation = 12`. Calls use `ReturnSingleEntry=FALSE`; the first
call uses `RestartScan=TRUE`, continuations use `FALSE`; the name filter is
NULL. `STATUS_SUCCESS` parses exactly `IO_STATUS_BLOCK.Information` bytes.
`STATUS_NO_MORE_FILES = 0x80000006` ends enumeration only after at least one
valid call and with no unparsed bytes; all other statuses fail closed.

`FILE_NAMES_INFORMATION` has a 12-byte header: `NextEntryOffset: ULONG` at 0,
`FileIndex: ULONG` at 4, `FileNameLength: ULONG` at 8, followed by
`FileName: WCHAR[]`. Require an even `FileNameLength`, complete header/name
within both `Information` and the supplied buffer, strict UTF-16, nonempty
single-component names, monotonic non-cycling progress, and case-folded
uniqueness. A nonzero `NextEntryOffset` is aligned, at least
`12 + FileNameLength`, is a multiple of 8 on this frozen x64 scope, and lands
in bounds; zero marks the sole final record and requires the name to end
exactly at `Information`. This intentionally fail-closed parser permits no
alignment padding after the final filename.

**Same-writer-handle produces the claim:** bounded short-write loop over the
writer handle (still open with `FILE_SHARE_READ`), `FlushFileBuffers`, seek to
0, then `ReadFile` expecting `expected_len + 1` (the `+1` proves EOF / no extra
bytes). Immediately after `FILE_CREATE`, capture identity and require
`Directory=FALSE`, nonreparse, non-delete-pending, `NumberOfLinks=1`, and
`EndOfFile=0`. `WriteFile` loops on bounded short writes, rejects zero progress,
and never submits or accumulates more than the precomputed canonical length.
After flush/seek/readback require the same identity and flags,
`NumberOfLinks=1`, and `EndOfFile=expected_len`. The `expected_len+1` request
must return exactly `expected_len`, and a following read must report EOF. The
writer stays open while a
**fresh, relative, read-only, share-compatible** handle independently rereads
(sect. 9), repeating identity, flags, link, EOF, cap, and byte checks.

## 8. Closed enum table (exact internal triggers, catchall)

| Fixed enum | Meaning | Exact internal trigger(s) |
|---|---|---|
| `RL_RC_COLLISION` | race found target at `FILE_CREATE` | `STATUS_OBJECT_NAME_COLLISION (0xC0000035)` |
| `RL_RC_NAME_NOT_FOUND` | required component or leaf missing | `STATUS_OBJECT_NAME_NOT_FOUND (0xC0000034)` outside the reserved absence probe |
| `RL_RC_PATH_NOT_FOUND` | required path invalid/missing/bad | `STATUS_OBJECT_PATH_INVALID (0xC0000039)`, `STATUS_OBJECT_PATH_NOT_FOUND (0xC000003A)`, `STATUS_OBJECT_PATH_SYNTAX_BAD (0xC000003B)` |
| `RL_RC_TYPE_MISMATCH` | dir-vs-file mismatch | `STATUS_OBJECT_TYPE_MISMATCH (0xC0000024)`, `STATUS_FILE_IS_A_DIRECTORY (0xC00000BA)`, `STATUS_NOT_A_DIRECTORY (0xC0000103)` |
| `RL_RC_ACCESS` | access/privilege/capability denied | `STATUS_ACCESS_DENIED` (0xC0000022) / `STATUS_PRIVILEGE_NOT_HELD` (0xC0000061) |
| `RL_RC_SHARING` | share violation | `STATUS_SHARING_VIOLATION` (0xC0000043) |
| `RL_RC_DELETE_PENDING` | delete pending | `STATUS_DELETE_PENDING (0xC0000056)` or same-HANDLE `DeletePending != 0` |
| `RL_RC_REPARSE` | any reparse encountered | `STATUS_REPARSE_POINT_ENCOUNTERED (0xC000050B)`, nonzero `ReparseTag`, or `FILE_ATTRIBUTE_REPARSE_POINT` |
| `RL_RC_DEVICE` | scope mismatch (UNC/mapped/SUBST/device/remote/WOW64) | scope precheck failure |
| `RL_RC_NATIVE_FAILURE` | **catchall** for any NTSTATUS not in this table | any unmapped status |
| `RL_RC_POSTCLAIM_CONSUMED` | any failure after claim object creation | all postclaim failures, regardless of internal cause |

The reserved absence probe treats only `STATUS_OBJECT_NAME_NOT_FOUND` as the
internal `absent` control outcome and emits no error enum. Access, sharing,
reparse, type, path, and all other probe failures retain their own mapping.
Preclaim mapping compares the original NTSTATUS directly; optional
`RtlNtStatusToDosError` output is internal diagnostics only. After
`claim_created=True`, all failures collapse externally to
`RL_RC_POSTCLAIM_CONSUMED`. No raw status, path, or exception text leaks.

## 9. Final independent reopen and lease graph

The claim writer handle **stays open**. A **fresh** relative reader opens the
same single component from the validity `RootDirectory` with DesiredAccess
`FILE_READ_DATA|FILE_READ_ATTRIBUTES|SYNCHRONIZE`, ShareAccess
`FILE_SHARE_READ|FILE_SHARE_WRITE` (no delete), disposition `FILE_OPEN`, and
options `FILE_NON_DIRECTORY_FILE|FILE_SYNCHRONOUS_IO_NONALERT|
FILE_OPEN_REPARSE_POINT`. Success requires `NT_SUCCESS`, a valid HANDLE, and
`IO_STATUS_BLOCK.Information == FILE_OPENED (1)`. These shares are explicitly
compatible with the still-open writer's WRITE access. Identity/EOF/bytes must
match. Any
post-claim divergence yields exactly **one fixed consumed code** (sect. 8 /
sect. 10).

**Lease graph:** retain the volume root and every component HANDLE for the repo
root, fixed inputs/toolchain, outputs, and validity for their full specified
lifetime. Shared ancestors use one refcounted graph, so no branch can close an
ancestor still used by another branch. Every child, including writer and fresh
reader, closes before its parent; the volume root closes last.

## 10. Failure handling and permanent-consumption policy

- **Preclaim zero-write:** before any mutation, the pipeline writes nothing and
  creates nothing; the first mutation is the relative `FILE_CREATE` of the
  claim leaf. Absence + enumeration are read-only.
- **Claim-created means consumed.** After a successful `FILE_CREATE`, if the
  object is 0-length, partial, or corrupt, the attempt is **permanently
  consumed**; no delete, recover, retry, or rewrite is permitted.
- **Success is forward-only** through results/verdict/index-last and the final
  read; the write closure is followed by the independent reopen, then success.
- **Any post-claim failure is close-only** and reports exactly **one fixed
  consumed code**; no path, no status, no exception text surfaces; no
  delete/recover/retry/rewrite.
- **Policy statement:** no **parent-dir fsync / power-loss directory-entry**
  guarantee is claimed; "permanent" is a **protocol policy only**, not an
  on-disk durability guarantee.

## 11. Synthetic fake tests (every claim prover)

Synthetic fake-DLL / fake-HANDLE tests (no real file in the workspace) cover
**every** ABI/option/status/identity/enumeration/concurrency/fault/lifecycle
claim: struct sizes; signoff/`IsWow64Process2`/`GetDriveTypeW DRIVE_FIXED`;
volume-root handle checks; every proto/argtype/restype frozen; root/dir/file
access/share/disposition/options; reparse rejection on all handles; all info
classes and `IO_STATUS_BLOCK` union; `NtQueryDirectoryFile`
`FILE_NAMES_INFORMATION (12)` parser/status/restart/no-more rules;
handle-relative absence + preclaimed enumeration; FileCreate options;
bounded short-write + flush + seek + `expected_len+1` EOF read; writer-open +
fresh read-only reopen; lease refcount graph order; split pre-probe vs
collision race; every enum hex in the closed table incl. `RL_RC_NATIVE_FAILURE`
catchall; permanent-consumption on 0/partial/corrupt; preclaim zero-write; and
post-claim close-only single-code failures. They **prove the first mutation is
the relative `FILE_CREATE`**.

## 12. Next step and forbidden actions

- **Allowed next step (post independent review only):** a separately frozen
  **authoritative acceptance** document may lift `STOP_IMPLEMENTATION` only if
  it records the ABI, sizes, relative-open rule, permanent-consumption policy,
  and closed enum table as correct.
- **Currently forbidden** (all hold until then): implementation; wiring of any
  runner or ABI shim; any test runner; protocol/outputs/schema; any data
  access; quarantined data; all GO semantics. Nothing here creates a run, and
  sect. 11 is a test list on fake handles only.

This proposal stays **PROPOSED / NOT_GO_RUN / STOP_IMPLEMENTATION** and
contains no parseable GO/envelope/claim instance.
