package com.github.chirilbinzaru.smartmute.export

import org.junit.Assert.assertEquals
import org.junit.Test

class CsvExporterTest {
    @Test
    fun plainFieldIsUnquoted() {
        assertEquals("hello world", CsvExporter.escape("hello world"))
    }

    @Test
    fun commaIsQuoted() {
        assertEquals("\"ok, see you\"", CsvExporter.escape("ok, see you"))
    }

    @Test
    fun quotesAreDoubled() {
        assertEquals("\"he said \"\"hi\"\"\"", CsvExporter.escape("he said \"hi\""))
    }

    @Test
    fun newlinesAreQuoted() {
        assertEquals("\"line1\nline2\"", CsvExporter.escape("line1\nline2"))
        assertEquals("\"a\r\nb\"", CsvExporter.escape("a\r\nb"))
    }

    @Test
    fun cyrillicPassesThrough() {
        assertEquals("Привет", CsvExporter.escape("Привет"))
    }

    @Test
    fun reasonNames() {
        assertEquals("CLICK", CsvExporter.removalReasonName(1))
        assertEquals("APP_CANCEL", CsvExporter.removalReasonName(8))
        assertEquals("UNKNOWN_99", CsvExporter.removalReasonName(99))
    }
}
