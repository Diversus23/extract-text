#!/usr/bin/env perl

# Тестовый файл Perl для проверки извлечения текста
# Демонстрирует структуру тестов в Perl

use strict;
use warnings;
use utf8;
use Test::More;
use Test::Exception;
use HTTP::Request::Common;
use LWP::UserAgent;
use JSON::PP;
use File::Temp qw/tempfile/;
use File::Slurp qw/write_file read_file/;
use Encode qw/decode encode/;

# Планирование количества тестов
plan tests => 25;

# Константы для тестирования
use constant {
    API_BASE_URL => 'http://localhost:7555',
    MAX_FILE_SIZE => 20 * 1024 * 1024,  # 20MB
    TIMEOUT => 30,
    TEST_FILES_DIR => './tests',
};

# Глобальные переменные
my $ua = LWP::UserAgent->new(timeout => TIMEOUT);
my $json = JSON::PP->new->utf8;

# Тестовые данные
my @test_cases = (
    {
        name => 'PDF файл',
        file => 'test.pdf',
        expected_words => 50,
        description => 'Тестирование извлечения текста из PDF документа'
    },
    {
        name => 'DOCX файл',
        file => 'test.docx',
        expected_words => 30,
        description => 'Тестирование извлечения текста из Word документа'
    },
    {
        name => 'Python код',
        file => 'test.py',
        expected_words => 100,
        description => 'Тестирование извлечения текста из исходного кода Python'
    },
    {
        name => '1С код',
        file => 'test.bsl',
        expected_words => 80,
        description => 'Тестирование извлечения текста из кода 1С:Предприятие'
    },
    {
        name => 'OneScript код',
        file => 'test.os',
        expected_words => 70,
        description => 'Тестирование извлечения текста из кода OneScript'
    }
);

# Функция для создания тестового файла
sub create_test_file {
    my ($filename, $content) = @_;
    my ($fh, $temp_file) = tempfile();
    write_file($temp_file, encode('utf-8', $content));
    close($fh);
    return $temp_file;
}

# Функция для отправки файла на API
sub send_file_to_api {
    my ($file_path, $filename) = @_;
    
    my $content = read_file($file_path, { binmode => ':raw' });
    
    my $request = HTTP::Request::Common::POST(
        API_BASE_URL . '/v1/extract-text/',
        Content_Type => 'multipart/form-data',
        Content => [
            file => [
                undef,
                $filename,
                Content => $content,
                Content_Type => 'application/octet-stream'
            ]
        ]
    );
    
    return $ua->request($request);
}

# Функция для проверки ответа API
sub check_api_response {
    my ($response, $test_name) = @_;
    
    ok($response->is_success, "$test_name: HTTP запрос успешен");
    
    if ($response->is_success) {
        my $data = eval { $json->decode($response->content) };
        ok(defined $data, "$test_name: Ответ в формате JSON");
        
        if (defined $data) {
            ok(exists $data->{text}, "$test_name: Поле 'text' присутствует");
            ok(exists $data->{word_count}, "$test_name: Поле 'word_count' присутствует");
            ok(exists $data->{character_count}, "$test_name: Поле 'character_count' присутствует");
            
            if (exists $data->{text}) {
                ok(length($data->{text}) > 0, "$test_name: Извлеченный текст не пустой");
            }
            
            if (exists $data->{word_count}) {
                ok($data->{word_count} > 0, "$test_name: Количество слов больше нуля");
            }
        }
    } else {
        diag("Ошибка API: " . $response->status_line);
        diag("Содержимое ответа: " . $response->content);
    }
}

# Тест 1: Проверка доступности API
subtest 'API доступности' => sub {
    my $response = $ua->get(API_BASE_URL . '/health');
    ok($response->is_success, 'Эндпоинт /health доступен');
    
    if ($response->is_success) {
        my $data = eval { $json->decode($response->content) };
        ok(defined $data, 'Ответ в формате JSON');
        is($data->{status}, 'ok', 'Статус системы: ok');
    }
};

# Тест 2: Проверка информации о API
subtest 'Информация о API' => sub {
    my $response = $ua->get(API_BASE_URL . '/');
    ok($response->is_success, 'Эндпоинт / доступен');
    
    if ($response->is_success) {
        my $data = eval { $json->decode($response->content) };
        ok(defined $data, 'Ответ в формате JSON');
        ok(exists $data->{api_name}, 'Поле api_name присутствует');
        ok(exists $data->{version}, 'Поле version присутствует');
        is($data->{version}, '1.7', 'Версия API: 1.7');
    }
};

# Тест 3: Проверка поддерживаемых форматов
subtest 'Поддерживаемые форматы' => sub {
    my $response = $ua->get(API_BASE_URL . '/v1/supported-formats');
    ok($response->is_success, 'Эндпоинт /v1/supported-formats доступен');
    
    if ($response->is_success) {
        my $data = eval { $json->decode($response->content) };
        ok(defined $data, 'Ответ в формате JSON');
        ok(exists $data->{source_code}, 'Категория source_code присутствует');
        
        if (exists $data->{source_code}) {
            my @source_formats = @{$data->{source_code}};
            ok(grep { $_ eq 'bsl' } @source_formats, 'Формат bsl поддерживается');
            ok(grep { $_ eq 'os' } @source_formats, 'Формат os поддерживается');
            ok(grep { $_ eq 'py' } @source_formats, 'Формат py поддерживается');
        }
    }
};

# Тест 4: Обработка файлов
for my $test_case (@test_cases) {
    subtest $test_case->{description} => sub {
        my $file_path = TEST_FILES_DIR . '/' . $test_case->{file};
        
        SKIP: {
            skip "Файл $file_path не найден", 4 unless -f $file_path;
            
            my $response = send_file_to_api($file_path, $test_case->{file});
            check_api_response($response, $test_case->{name});
        }
    };
}

# Тест 5: Обработка ошибок
subtest 'Обработка ошибок' => sub {
    # Отправка слишком большого файла
    my $large_content = 'x' x (MAX_FILE_SIZE + 1);
    my $large_file = create_test_file('large.txt', $large_content);
    
    my $response = send_file_to_api($large_file, 'large.txt');
    ok(!$response->is_success, 'Большой файл отклонен');
    is($response->code, 413, 'Код ошибки 413 для большого файла');
    
    unlink($large_file);
    
    # Отправка неподдерживаемого формата
    my $unsupported_content = 'test content';
    my $unsupported_file = create_test_file('test.unknown', $unsupported_content);
    
    $response = send_file_to_api($unsupported_file, 'test.unknown');
    ok(!$response->is_success, 'Неподдерживаемый формат отклонен');
    is($response->code, 415, 'Код ошибки 415 для неподдерживаемого формата');
    
    unlink($unsupported_file);
};

# Тест 6: Производительность
subtest 'Производительность' => sub {
    my $start_time = time();
    
    # Создание среднего файла для тестирования
    my $medium_content = 'Тестовый текст для проверки производительности. ' x 1000;
    my $medium_file = create_test_file('medium.txt', $medium_content);
    
    my $response = send_file_to_api($medium_file, 'medium.txt');
    my $end_time = time();
    my $processing_time = $end_time - $start_time;
    
    ok($response->is_success, 'Файл успешно обработан');
    ok($processing_time < TIMEOUT, 'Обработка завершена в пределах таймаута');
    
    diag("Время обработки: ${processing_time}с");
    
    unlink($medium_file);
};

# Финализация тестов
done_testing();

# Функция для очистки после тестов
END {
    diag("Тестирование завершено");
}

__END__

=head1 NAME

test.t - Тесты для API извлечения текста

=head1 DESCRIPTION

Этот файл содержит набор тестов для проверки функциональности API
извлечения текста из файлов различных форматов.

=head1 TESTS

=over 4

=item * API доступности

Проверяет доступность основных эндпоинтов API

=item * Информация о API

Проверяет корректность информации о версии и названии API

=item * Поддерживаемые форматы

Проверяет список поддерживаемых форматов файлов

=item * Обработка файлов

Тестирует извлечение текста из различных типов файлов

=item * Обработка ошибок

Проверяет корректную обработку ошибочных ситуаций

=item * Производительность

Проверяет производительность обработки файлов

=back

=head1 AUTHOR

Барилко Виталий

=head1 VERSION

1.0

=cut 